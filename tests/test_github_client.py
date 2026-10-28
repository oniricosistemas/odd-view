import httpx
import pytest

from ai_reviewer.github import GitHubClient, ReviewTooLarge


@pytest.mark.asyncio
async def test_files_are_paginated_without_following_link_urls():
    seen = []
    async def handler(request):
        seen.append(str(request.url))
        page = request.url.params.get("page")
        headers = {"Link": '<https://evil.invalid/steal>; rel="next"'} if page == "1" else {}
        return httpx.Response(200, json=[{"filename": f"f{page}"}], headers=headers)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com",
                                 follow_redirects=False) as raw:
        gh = GitHubClient(raw, lambda: async_token("tok"))
        files = await gh.pr_files("owner/repo", 4)
    assert [f["filename"] for f in files] == ["f1", "f2"]
    assert all(url.startswith("https://api.github.com/repos/owner/repo/pulls/4/files") for url in seen)


async def async_token(value):
    return value


@pytest.mark.asyncio
async def test_redirect_response_is_rejected():
    async def handler(request):
        return httpx.Response(302, headers={"Location": "https://evil.invalid"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com",
                                 follow_redirects=False) as raw:
        gh = GitHubClient(raw, lambda: async_token("tok"))
        with pytest.raises(httpx.HTTPStatusError):
            await gh.get_pr("owner/repo", 4)


@pytest.mark.asyncio
async def test_check_runs_are_paginated_on_fixed_api_paths():
    seen = []
    async def handler(request):
        seen.append(str(request.url))
        page = request.url.params.get("page")
        headers = {"Link": '<https://evil.invalid/next>; rel="next"'} if page == "1" else {}
        return httpx.Response(200, json={"check_runs": [{"id": int(page)}]}, headers=headers)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com",
                                 follow_redirects=False) as raw:
        result = await GitHubClient(raw, lambda: async_token("tok")).check_runs("owner/repo", "a" * 40)
    assert [item["id"] for item in result] == [1, 2]
    assert all("api.github.com/repos/owner/repo/commits/" in url for url in seen)


@pytest.mark.asyncio
async def test_github_response_content_length_and_stream_are_bounded():
    consumed = 0
    class Huge(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal consumed
            for _ in range(20):
                consumed += 1
                yield b"x" * (1024 * 1024)
    calls = 0
    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, headers={"Content-Length": str(9 * 1024 * 1024)}, content=b"")
        return httpx.Response(200, stream=Huge())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as raw:
        gh = GitHubClient(raw, lambda: async_token("tok"))
        with pytest.raises(ValueError, match="too large"):
            await gh.get_pr("owner/repo", 4)
        with pytest.raises(ValueError, match="too large"):
            await gh.get_pr("owner/repo", 4)
    assert consumed <= 9


def test_github_client_refuses_redirect_following_configuration():
    raw = httpx.AsyncClient(base_url="https://api.github.com", follow_redirects=True)
    try:
        with pytest.raises(ValueError, match="redirect"):
            GitHubClient(raw, lambda: async_token("tok"))
    finally:
        import asyncio
        asyncio.run(raw.aclose())


@pytest.mark.asyncio
async def test_files_stop_streaming_pages_before_more_than_300_items_are_materialized():
    pages = 0
    async def handler(request):
        nonlocal pages
        pages += 1
        return httpx.Response(200, json=[{"filename": f"f{pages}-{i}", "patch": "+x"} for i in range(100)],
                              headers={"Link": '<fixed>; rel="next"'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as raw:
        with pytest.raises(ReviewTooLarge, match="file count"):
            await GitHubClient(raw, lambda: async_token("tok")).pr_files("owner/repo", 4)
    assert pages == 3


@pytest.mark.asyncio
async def test_files_stop_on_aggregate_bytes_during_pagination():
    pages = 0
    async def handler(request):
        nonlocal pages
        pages += 1
        return httpx.Response(200, json=[{"filename": f"f{pages}", "patch": "x" * 300_000}],
                              headers={"Link": '<fixed>; rel="next"'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as raw:
        with pytest.raises(ReviewTooLarge, match="aggregate bytes"):
            await GitHubClient(raw, lambda: async_token("tok")).pr_files("owner/repo", 4)
    assert pages == 2
