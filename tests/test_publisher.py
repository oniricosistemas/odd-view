import re

import httpx
import pytest

from ai_reviewer.github import GitHubClient
from ai_reviewer.contracts import Finding
from ai_reviewer.publisher import ManualReconciliationRequired, Publisher, StaleHead
from ai_reviewer.reducer import ReducedFinding


async def token(): return "tok"


def test_publication_summary_is_in_spanish():
    snapshot = Publisher(None, b"server-marker-secret", 42, 7).render_snapshot(
        "o/r", 3, "abc", "v1", []
    )
    assert snapshot["review_payload"]["body"].startswith("Revisión de IA completada.\n")
    assert snapshot["check_payload"]["output"] == {
        "title": "Revisión de IA completada",
        "summary": "Hallazgos encontrados: 0.",
    }


def test_completed_publication_contract_is_comment_named_ai_pr_review_and_success():
    snapshot = Publisher(None, b"server-marker-secret", 42, 7).render_snapshot(
        "o/r", 3, "abc", "v1", []
    )
    assert snapshot["review_payload"]["event"] == "COMMENT"
    assert snapshot["check_payload"]["name"] == "AI PR Review"
    assert snapshot["check_payload"]["status"] == "completed"
    assert snapshot["check_payload"]["conclusion"] == "success"


@pytest.mark.asyncio
async def test_publication_reconciles_one_comment_review_and_check_exact_sha():
    posts = []
    async def handler(request):
        path = request.url.path
        if request.method == "GET" and path.endswith("/pulls/3"):
            return httpx.Response(200, json={"state": "open", "draft": False, "head": {"sha": "abc"}})
        if request.method == "GET" and path.endswith("/pulls/3/reviews"):
            return httpx.Response(200, json=[p[1] for p in posts if p[0] == "review"])
        if request.method == "GET" and path.endswith("/commits/abc/check-runs"):
            return httpx.Response(200, json={"check_runs": [p[1] for p in posts if p[0] == "check"]})
        payload = __import__("json").loads(request.content)
        if path.endswith("/pulls/3/reviews"):
            assert payload["event"] == "COMMENT" and payload["commit_id"] == "abc"
            value = {"id": 10, "body": payload["body"], "commit_id": "abc", "user": {"id": 42}}
            posts.append(("review", value))
            return httpx.Response(200, json=value)
        assert path.endswith("/check-runs") and payload["head_sha"] == "abc"
        value = {"id": 20, "external_id": payload["external_id"], "head_sha": "abc", "app": {"id": 7}}
        posts.append(("check", value))
        return httpx.Response(201, json=value)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as raw:
        publisher = Publisher(GitHubClient(raw, token), b"server-marker-secret", 42, 7)
        first = await publisher.publish("o/r", 3, "abc", "v1", [])
        second = await publisher.publish("o/r", 3, "abc", "v1", [])
    assert first == second == (10, 20)
    assert [kind for kind, _ in posts] == ["review", "check"]


@pytest.mark.asyncio
async def test_stale_head_is_never_published():
    async def handler(request):
        return httpx.Response(200, json={"state": "open", "draft": False, "head": {"sha": "new"}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as raw:
        with pytest.raises(StaleHead):
            await Publisher(GitHubClient(raw, token), b"server-marker-secret", 42, 7).publish("o/r", 3, "old", "v1", [])


@pytest.mark.asyncio
async def test_reconciliation_rejects_spoofed_identity_and_sanitizes_hostile_output():
    posts = []
    finding = Finding(candidate_id="c", rule_id="r", severity="high", confidence=1,
        path="a.py", line=1, side="RIGHT", title="@admin <img src=x>",
        evidence="![x](https://evil.invalid/a) https://evil.invalid", impact="<b>boom</b>",
        recommendation="ping @team", root_cause_key="r")
    async def handler(request):
        path = request.url.path
        if request.method == "GET" and path.endswith("/pulls/3"):
            return httpx.Response(200, json={"state": "open", "draft": False, "head": {"sha": "abc"}})
        if request.method == "GET" and path.endswith("/pulls/3/reviews"):
            marker, _ = Publisher.identity("o/r", 3, "abc", "v1", b"server-marker-secret")
            return httpx.Response(200, json=[{"id": 1, "body": marker, "commit_id": "abc", "user": {"id": 999}}])
        if request.method == "GET" and path.endswith("/commits/abc/check-runs"):
            return httpx.Response(200, json={"check_runs": []})
        payload = __import__("json").loads(request.content); posts.append(payload)
        if "reviews" in path:
            return httpx.Response(201, json={"id": 10, "body": payload["body"], "commit_id": "abc", "user": {"id": 42}})
        return httpx.Response(201, json={"id": 20, "external_id": payload["external_id"],
                                         "head_sha": "abc", "app": {"id": 7}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as raw:
        await Publisher(GitHubClient(raw, token), b"server-marker-secret", 42, 7).publish(
            "o/r", 3, "abc", "v1", [ReducedFinding(finding, "fp")])
    comment = posts[0]["comments"][0]["body"]
    assert "Impacto:" in comment
    assert "Recomendación:" in comment
    assert "Huella:" in comment
    assert "Impact:" not in comment and "Recommendation:" not in comment and "Fingerprint:" not in comment
    assert "@admin" not in comment and "<img" not in comment and "https://" not in comment
    assert posts[0]["event"] == "COMMENT"


@pytest.mark.parametrize("hostile", [
    "//evil.invalid/path", "ftp://evil.invalid/x", "mailto:a@evil.invalid",
    "data:text/html,boom", "javascript:alert(1)", "<https://evil.invalid>",
    "www.evil.invalid/path", "<www.evil.invalid/path>",
    "[click](https://evil.invalid)", "![pixel](//evil.invalid/p.png)",
    '<a href="https://evil.invalid">read me</a>',
])
def test_sanitizer_neutralizes_every_active_remote_form_and_mentions(hostile):
    safe = Publisher._safe(hostile + " @admins")
    lowered = safe.lower()
    assert "@admins" not in safe
    assert not re.search(r"(?i)(?:https?|ftp|mailto|data|javascript):|(?<!:)//|\bwww\.", safe)
    assert "](" not in safe
    assert "href=" not in lowered and "<a" not in lowered and "<img" not in lowered
    assert any(word in safe for word in ("evil.invalid", "click", "pixel", "read me", "blocked", "data", "alert"))


@pytest.mark.asyncio
async def test_ambiguous_review_waits_with_deterministic_backoff_until_visible_and_never_reposts():
    sleeps = []
    posts = 0
    reads_after_post = 0
    marker, external_id = Publisher.identity("o/r", 3, "abc", "v1", b"server-marker-secret")

    class GitHub:
        async def get_pr(self, repo, pull):
            return {"state": "open", "draft": False, "head": {"sha": "abc"}}
        async def list_reviews(self, repo, pull):
            nonlocal reads_after_post
            if posts:
                reads_after_post += 1
            return ([{"id": 10, "body": marker, "commit_id": "abc", "user": {"id": 42}}]
                    if reads_after_post >= 3 else [])
        async def create_review(self, repo, pull, payload):
            nonlocal posts
            posts += 1
            raise httpx.ReadTimeout("response lost")
        async def check_runs(self, repo, sha):
            return [{"id": 20, "external_id": external_id, "head_sha": sha, "app": {"id": 7}}]

    async def sleep(delay):
        sleeps.append(delay)

    publisher = Publisher(GitHub(), b"server-marker-secret", 42, 7,
                          reconciliation_delays=(1, 2, 4, 8), sleep=sleep,
                          jitter=lambda delay, attempt: delay + attempt / 10)
    assert await publisher.publish("o/r", 3, "abc", "v1", []) == (10, 20)
    assert posts == 1
    assert sleeps == [1.0, 2.1, 4.2]


@pytest.mark.asyncio
async def test_ambiguous_review_treats_finder_timeouts_as_ambiguous_and_never_reposts():
    posts = 0
    reads_after_post = 0
    marker, external_id = Publisher.identity("o/r", 3, "abc", "v1", b"server-marker-secret")

    class GitHub:
        async def get_pr(self, repo, pull):
            return {"state": "open", "draft": False, "head": {"sha": "abc"}}

        async def list_reviews(self, repo, pull):
            nonlocal reads_after_post
            if not posts:
                return []
            reads_after_post += 1
            if reads_after_post == 1:
                raise httpx.ReadTimeout("reconciliation read timed out")
            return [{"id": 10, "body": marker, "commit_id": "abc", "user": {"id": 42}}]

        async def create_review(self, repo, pull, payload):
            nonlocal posts
            posts += 1
            raise httpx.ReadTimeout("response lost after remote commit")

        async def check_runs(self, repo, sha):
            return [{"id": 20, "external_id": external_id, "head_sha": sha, "app": {"id": 7}}]

    publisher = Publisher(
        GitHub(), b"server-marker-secret", 42, 7,
        reconciliation_delays=(0, 0, 0),
        sleep=lambda delay: __import__("asyncio").sleep(0),
        jitter=lambda delay, attempt: delay,
    )
    assert await publisher.publish("o/r", 3, "abc", "v1", []) == (10, 20)
    assert posts == 1
    assert reads_after_post == 2


@pytest.mark.asyncio
async def test_ambiguous_review_exhaustion_requires_manual_reconciliation_without_second_post():
    posts = 0
    progress = []

    class GitHub:
        async def get_pr(self, repo, pull):
            return {"state": "open", "draft": False, "head": {"sha": "abc"}}
        async def list_reviews(self, repo, pull):
            return []
        async def create_review(self, repo, pull, payload):
            nonlocal posts
            posts += 1
            raise httpx.ReadTimeout("response lost")

    publisher = Publisher(GitHub(), b"server-marker-secret", 42, 7,
                          reconciliation_delays=(0.01, 0.02, 0.03),
                          sleep=lambda delay: __import__("asyncio").sleep(0))
    with pytest.raises(ManualReconciliationRequired, match="review"):
        await publisher.publish("o/r", 3, "abc", "v1", [], on_ambiguity=lambda **state: progress.append(state))
    assert posts == 1
    assert [item["attempts"] for item in progress] == [0, 1, 2, 3]
