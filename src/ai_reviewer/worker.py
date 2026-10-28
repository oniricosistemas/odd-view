import asyncio
import json
import re

from .contracts import FindingBatch, SuggestionBatch, VerificationBatch, validate_locations
from .github import GitHubClient, ReviewTooLarge
from .omniroute import OmniRouteClient
from .pipeline import plan_passes
from .publisher import ManualReconciliationRequired, Publisher, StaleHead
from .reducer import reduce_findings
from .store import LeaseLost, Store

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_MAX_PR_CHARS = 500_000
_MAX_PR_BYTES = 512 * 1024
_MAX_SERIALIZED_PROMPT_BYTES = 1024 * 1024


def prompt_json(payload: dict) -> str:
    result = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    if len(result.encode("utf-8")) > _MAX_SERIALIZED_PROMPT_BYTES:
        raise ValueError("serialized prompt exceeds limit; analysis is incomplete")
    return result


def bounded_pr_data(data: dict) -> dict:
    title = data.get("title") or ""
    body = data.get("body") or ""
    files = data.get("files")
    if not isinstance(title, str) or len(title) > 500:
        raise ValueError("PR title exceeds prompt limit")
    if not isinstance(body, str) or len(body) > 20_000:
        raise ValueError("PR body exceeds prompt limit")
    if not isinstance(files, list) or len(files) > 300:
        raise ValueError("PR files exceed prompt limit")
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("invalid PR files entry")
        filename, patch = item.get("filename"), item.get("patch")
        if not isinstance(filename, str) or len(filename) > 512:
            raise ValueError("PR filename exceeds prompt limit")
        if patch is not None and (not isinstance(patch, str) or len(patch) > 50_000):
            raise ValueError("PR patch exceeds prompt limit")
    strings = [title, body]
    for item in files:
        strings.append(item.get("filename", ""))
        if item.get("patch") is not None:
            strings.append(item["patch"])
    chars = sum(len(value) for value in strings)
    encoded = sum(len(value.encode("utf-8")) for value in strings)
    if chars > _MAX_PR_CHARS or encoded > _MAX_PR_BYTES or (chars + 3) // 4 > 125_000:
        raise ValueError("PR aggregate exceeds prompt limit; analysis is incomplete")
    return {"title": title, "body": body, "files": files}


def canonicalize_findings(role: str, batch: FindingBatch) -> list:
    raw_ids = [finding.candidate_id for finding in batch.findings]
    if len(raw_ids) != len(set(raw_ids)):
        raise ValueError("duplicate candidate id in pass")
    canonical = []
    for finding in batch.findings:
        candidate_id = f"{role}:{finding.candidate_id}"
        if len(candidate_id) > 128:
            raise ValueError("canonical candidate id exceeds contract limit")
        canonical.append(finding.model_copy(update={"candidate_id": candidate_id}))
    return canonical


def patch_lines(files: list[dict]) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    for file in files:
        path, patch = file.get("filename"), file.get("patch")
        if not isinstance(path, str) or not isinstance(patch, str):
            continue
        valid: set[int] = set()
        current: int | None = None
        for text in patch.splitlines():
            match = _HUNK.match(text)
            if match:
                current = int(match.group(1))
            elif current is not None and not text.startswith("-") and not text.startswith("\\"):
                valid.add(current)
                current += 1
        result[path] = valid
    return result


class Worker:
    def __init__(self, store: Store, github: GitHubClient, omni: OmniRouteClient,
                 marker_secret: bytes, expected_review_author_id: int, expected_check_app_id: int):
        self.store = store
        self.github = github
        self.omni = omni
        self.publisher = Publisher(github, marker_secret, expected_review_author_id, expected_check_app_id)

    async def process(self, run_id: int, owner: str, generation: int, *, lease_seconds: int = 300) -> None:
        run = self.store.get_run(run_id)
        if (run["status"] != "running" or run["lease_owner"] != owner
                or run["lease_generation"] != generation):
            raise LeaseLost(run_id)
        repo = run["pending_repository_full_name"] or run["repository_full_name"]
        installation_id = run["pending_installation_id"] or run["installation_id"]
        pull, sha = run["pull_number"], run["head_sha"]
        lease_lost = asyncio.Event()

        async def renew() -> None:
            while True:
                await asyncio.sleep(max(1, lease_seconds // 3))
                if not self.store.heartbeat(run_id, owner, generation, lease_seconds=lease_seconds):
                    lease_lost.set()
                    return

        def ensure_lease() -> None:
            if lease_lost.is_set() or not self.store.heartbeat(
                    run_id, owner, generation, lease_seconds=lease_seconds):
                raise LeaseLost(run_id)

        heartbeat = asyncio.create_task(renew())
        try:
            ensure_lease()
            if run["pending_installation_id"] is not None:
                metadata_pr = await self.github.get_pr(repo, pull)
                live_repo = metadata_pr.get("base", {}).get("repo", {})
                if (live_repo.get("id") != run["repository_id"]
                        or live_repo.get("full_name") != repo):
                    raise RuntimeError("pending repository metadata was not confirmed by GitHub")
                self.store.confirm_metadata(run_id, owner, generation, installation_id, repo)
            if run["snapshot_json"] is not None:
                snapshot_text = run["snapshot_json"]
                snapshot = json.loads(snapshot_text)
                publication = self.store.acquire_publication(
                    run_id, owner, generation, publication_owner=owner,
                    snapshot_json=snapshot_text, lock_seconds=lease_seconds)
                if publication is None:
                    raise LeaseLost(run_id)

                def saved_progress(**ids):
                    self.store.record_publication(
                        run_id, owner, generation, publication_owner=publication["owner"],
                        publication_generation=publication["generation"], **ids)

                def saved_guard():
                    ensure_lease()
                    if not self.store.heartbeat_publication(
                            run_id, owner, generation, publication["owner"],
                            publication["generation"], lock_seconds=lease_seconds):
                        raise LeaseLost(run_id)

                def saved_ambiguity(**state):
                    ensure_lease()
                    self.store.record_ambiguity(run_id, owner, generation, **state)

                review_id, check_id = await self.publisher.publish_snapshot(
                    repo, pull, sha, snapshot, on_progress=saved_progress, guard=saved_guard,
                    on_ambiguity=saved_ambiguity)
                saved_guard()
                self.store.finalize_publication(
                    run_id, owner, generation, publication["owner"], publication["generation"],
                    result_json=json.dumps(snapshot["result"], separators=(",", ":")),
                    review_id=review_id, check_id=check_id)
                return
            pr = await self.github.get_pr(repo, pull)
            ensure_lease()
            if pr.get("state") != "open" or pr.get("draft") or pr.get("head", {}).get("sha") != sha:
                raise StaleHead("pull request changed")
            files = await self.github.pr_files(repo, pull)
            ensure_lease()
            locations = patch_lines(files)
            paths = list(locations)
            pr_data = bounded_pr_data({"title": pr.get("title"), "body": pr.get("body"), "files": files})
            untrusted = prompt_json(pr_data)
            passes = plan_passes(paths, untrusted)
            findings = []
            verifications = []
            for review_pass in passes:
                if review_pass.role == "primary":
                    prompt = prompt_json({"task": "find_defects", "schema": FindingBatch.model_json_schema(),
                                          "pr_data": pr_data})
                    batch = await self.omni.complete(review_pass.model, prompt, FindingBatch)
                    findings.extend(canonicalize_findings(review_pass.role, batch))
                elif review_pass.role == "adversarial":
                    validate_locations(findings, locations)
                    prompt = prompt_json({"task": "verify_findings",
                                          "schema": VerificationBatch.model_json_schema(),
                                          "pr_data": pr_data,
                                          "candidates": [item.model_dump(mode="json") for item in findings]})
                    verifications.extend((await self.omni.complete(
                        review_pass.model, prompt, VerificationBatch)).verifications)
                elif review_pass.role.endswith("specialist"):
                    prompt = prompt_json({"task": "find_specialist_defects",
                                          "schema": FindingBatch.model_json_schema(), "pr_data": pr_data,
                                          "specialist_rule": "security-sensitive path selected by local policy"})
                    specialist = canonicalize_findings(review_pass.role, await self.omni.complete(
                        review_pass.model, prompt, FindingBatch))
                    validate_locations(specialist, locations)
                    findings.extend(specialist)
                    verify_prompt = prompt_json({"task": "verify_findings",
                        "verification_rule": "independently confirm specialist evidence",
                        "schema": VerificationBatch.model_json_schema(), "pr_data": pr_data,
                        "candidates": [item.model_dump(mode="json") for item in specialist]})
                    verifications.extend((await self.omni.complete(
                        "OpenCode-Free", verify_prompt, VerificationBatch)).verifications)
                else:
                    prompt = prompt_json({"task": "suggest_wording_only",
                                          "schema": SuggestionBatch.model_json_schema(), "pr_data": pr_data})
                    await self.omni.complete(review_pass.model, prompt, SuggestionBatch)
                ensure_lease()
            validate_locations(findings, locations)
            reduced = reduce_findings(findings, verifications, locations)
            ensure_lease()
            snapshot = self.publisher.render_snapshot(repo, pull, sha, run["policy_version"], reduced)
            snapshot_text = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            publication = self.store.acquire_publication(
                    run_id, owner, generation, publication_owner=owner,
                    snapshot_json=snapshot_text, lock_seconds=lease_seconds)
            if not publication:
                raise LeaseLost(run_id)

            def progress(**ids):
                self.store.record_publication(
                    run_id, owner, generation, publication_owner=publication["owner"],
                    publication_generation=publication["generation"], **ids)

            def publication_guard():
                ensure_lease()
                if not self.store.heartbeat_publication(
                        run_id, owner, generation, publication["owner"],
                        publication["generation"], lock_seconds=lease_seconds):
                    raise LeaseLost(run_id)

            def publication_ambiguity(**state):
                ensure_lease()
                self.store.record_ambiguity(run_id, owner, generation, **state)

            review_id, check_id = await self.publisher.publish_snapshot(
                repo, pull, sha, snapshot, on_progress=progress, guard=publication_guard,
                on_ambiguity=publication_ambiguity)
            publication_guard()
            self.store.finalize_publication(
                run_id, owner, generation, publication["owner"], publication["generation"],
                result_json=json.dumps(snapshot["result"], separators=(",", ":")),
                review_id=review_id, check_id=check_id)
        except StaleHead:
            self.store.cancel_owned(run_id, owner, generation)
            raise
        except LeaseLost:
            raise
        except ManualReconciliationRequired as exc:
            self.store.mark_ambiguous(run_id, owner, generation, kind=exc.kind, attempts=exc.attempts)
            raise
        except ReviewTooLarge:
            self.store.update_owned(
                run_id, owner, generation, status="incomplete",
                result_json=json.dumps({"conclusion": "neutral", "reason": "review_too_large"},
                                       sort_keys=True, separators=(",", ":")))
            raise
        except Exception:
            self.store.fail_and_retry(run_id, owner, generation)
            raise
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
