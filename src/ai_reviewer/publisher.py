import hashlib
import hmac
import html
import re
import asyncio

from .github import GitHubClient
from .reducer import ReducedFinding


class StaleHead(RuntimeError):
    pass


class ManualReconciliationRequired(RuntimeError):
    def __init__(self, kind: str, attempts: int):
        super().__init__(f"{kind} publication is ambiguous; manual reconciliation required")
        self.kind = kind
        self.attempts = attempts


class Publisher:
    def __init__(self, github: GitHubClient, marker_secret: bytes,
                 expected_review_author_id: int, expected_check_app_id: int, *,
                 reconciliation_delays: tuple[float, ...] = (0.5, 1, 2, 4, 8, 16, 30),
                 sleep=asyncio.sleep, jitter=None):
        self.github = github
        self.marker_secret = marker_secret
        self.expected_review_author_id = expected_review_author_id
        self.expected_check_app_id = expected_check_app_id
        self.reconciliation_delays = reconciliation_delays
        self.sleep = sleep
        self.jitter = jitter or (lambda delay, attempt: delay * (1 + ((attempt * 37 + 17) % 101) / 1000))

    @staticmethod
    def identity(repo: str, pull: int, sha: str, policy: str, secret: bytes) -> tuple[str, str]:
        digest = hmac.new(secret, f"{repo}\0{pull}\0{sha}\0{policy}".encode(), hashlib.sha256).hexdigest()[:32]
        return f"<!-- ai-reviewer:{digest} -->", f"ai-reviewer:{digest}"

    @staticmethod
    def _safe(value: str) -> str:
        # Keep human-readable labels/text while removing every Markdown/HTML activation surface.
        value = re.sub(r"<((?:(?:[a-z][a-z0-9+.-]*:|//)|www\.)[^<>]+)>", r"\1", value,
                       flags=re.IGNORECASE)
        value = re.sub(r"<[^>]*>", "", value)
        value = re.sub(r"!?\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)", r"\1 [blocked link]", value)
        value = re.sub(r"(?i)\b([a-z][a-z0-9+.-]*):", r"\1[:]", value)
        value = re.sub(r"(?i)\bwww\.", "www[.]", value)
        value = re.sub(r"(?<!:)//", "/ /", value)
        value = html.escape(value, quote=False)
        return value.replace("@", "@\u200b")

    async def _assert_live(self, repo: str, pull: int, sha: str) -> None:
        pr = await self.github.get_pr(repo, pull)
        if pr.get("state") != "open" or pr.get("draft") or pr.get("head", {}).get("sha") != sha:
            raise StaleHead("pull request head/state changed")

    async def publish(self, repo: str, pull: int, head_sha: str, policy_version: str,
                      findings: list[ReducedFinding], on_progress=None, guard=None,
                      on_ambiguity=None) -> tuple[int, int]:
        snapshot = self.render_snapshot(repo, pull, head_sha, policy_version, findings)
        return await self.publish_snapshot(repo, pull, head_sha, snapshot,
                                           on_progress=on_progress, guard=guard,
                                           on_ambiguity=on_ambiguity)

    def render_snapshot(self, repo: str, pull: int, head_sha: str, policy_version: str,
                        findings: list[ReducedFinding]) -> dict:
        marker, external_id = self.identity(repo, pull, head_sha, policy_version, self.marker_secret)
        comments = [{"path": item.finding.path, "line": item.finding.line,
                     "side": item.finding.side,
                     "body": f"**{self._safe(item.finding.title)}**\n\n{self._safe(item.finding.evidence)}\n\n"
                             f"Impact: {self._safe(item.finding.impact)}\n\n"
                             f"Recommendation: {self._safe(item.finding.recommendation)}\n\n"
                             f"Fingerprint: `{item.fingerprint}`"}
                    for item in findings]
        return {
            "marker": marker,
            "external_id": external_id,
            "review_payload": {"commit_id": head_sha, "event": "COMMENT",
                               "body": f"AI review complete.\n{marker}", "comments": comments},
            "check_payload": {"name": "AI Review", "head_sha": head_sha,
                              "external_id": external_id, "status": "completed",
                              "conclusion": "neutral", "output": {"title": "AI review complete",
                              "summary": f"{len(findings)} finding(s)."}},
            "result": [item.fingerprint for item in findings],
        }

    async def publish_snapshot(self, repo: str, pull: int, head_sha: str, snapshot: dict,
                               on_progress=None, guard=None, on_ambiguity=None) -> tuple[int, int]:
        await self._assert_live(repo, pull, head_sha)
        marker, external_id = snapshot["marker"], snapshot["external_id"]
        review_payload, check_payload = snapshot["review_payload"], snapshot["check_payload"]
        if (review_payload.get("commit_id") != head_sha or check_payload.get("head_sha") != head_sha
                or marker not in review_payload.get("body", "")
                or check_payload.get("external_id") != external_id):
            raise ValueError("invalid publication snapshot")
        async def find_review():
            reviews = await self.github.list_reviews(repo, pull)
            return next((item for item in reviews if marker in (item.get("body") or "")
                         and item.get("commit_id") == head_sha
                         and item.get("user", {}).get("id") == self.expected_review_author_id), None)

        async def find_check():
            checks = await self.github.check_runs(repo, head_sha)
            return next((item for item in checks if item.get("external_id") == external_id
                         and item.get("head_sha") == head_sha
                         and item.get("app", {}).get("id") == self.expected_check_app_id), None)

        async def reconcile_ambiguous(kind, finder):
            if on_ambiguity is not None:
                on_ambiguity(kind=kind, attempts=0)
            for attempt, delay in enumerate(self.reconciliation_delays):
                await self.sleep(self.jitter(float(delay), attempt))
                try:
                    found = await finder()
                except Exception:
                    # Once a POST result is ambiguous, a failed reconciliation read
                    # must never reopen the POST path. Keep polling and eventually
                    # require manual reconciliation instead of risking a duplicate.
                    found = None
                if on_ambiguity is not None:
                    on_ambiguity(kind=kind, attempts=attempt + 1)
                if found is not None:
                    return found
            raise ManualReconciliationRequired(kind, len(self.reconciliation_delays))

        review = await find_review()
        if review is None:
            await self._assert_live(repo, pull, head_sha)
            if guard is not None:
                guard()
            try:
                review = await self.github.create_review(repo, pull, review_payload)
            except Exception:
                review = await reconcile_ambiguous("review", find_review)
            if on_progress is not None:
                on_progress(review_id=int(review["id"]))
            if guard is not None:
                guard()
            await self._assert_live(repo, pull, head_sha)
        check = await find_check()
        if check is None:
            await self._assert_live(repo, pull, head_sha)
            if guard is not None:
                guard()
            try:
                check = await self.github.create_check(repo, check_payload)
            except Exception:
                check = await reconcile_ambiguous("check", find_check)
            if on_progress is not None:
                on_progress(check_id=int(check["id"]))
            if guard is not None:
                guard()
            await self._assert_live(repo, pull, head_sha)
        return int(review["id"]), int(check["id"])
