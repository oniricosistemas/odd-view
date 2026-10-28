import base64
import json
import time
from datetime import datetime

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

API_VERSION = "2022-11-28"
MAX_GITHUB_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_TOKEN_RESPONSE_BYTES = 256 * 1024
MAX_PR_FILES = 300
MAX_PR_FILES_BYTES = 512 * 1024


class ReviewTooLarge(ValueError):
    pass


async def _bounded_send(client: httpx.AsyncClient, request: httpx.Request,
                        maximum: int, label: str) -> httpx.Response:
    response = await client.send(request, stream=True)
    try:
        response.raise_for_status()
        length = response.headers.get("Content-Length")
        if length is not None and int(length) > maximum:
            raise ValueError(f"{label} response too large")
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > maximum:
                raise ValueError(f"{label} response too large")
            chunks.append(chunk)
        return httpx.Response(response.status_code, headers=response.headers,
                              content=b"".join(chunks), request=request)
    finally:
        await response.aclose()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_app_jwt(app_id: str, private_key_pem: bytes, *, now: int | None = None) -> str:
    now = int(time.time()) if now is None else now
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"iat": now - 60, "exp": now + 540, "iss": app_id}, separators=(",", ":")).encode())
    unsigned = f"{header}.{payload}".encode()
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    signature = key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())
    return f"{unsigned.decode()}.{_b64(signature)}"


class GitHubAuth:
    def __init__(self, app_id: str, private_key: bytes, client: httpx.AsyncClient,
                 clock=time.time):
        if client.follow_redirects:
            raise ValueError("GitHub client must not follow redirects")
        self.app_id = app_id
        self.private_key = private_key
        self.client = client
        self.clock = clock
        self.cache: dict[int, tuple[str, float]] = {}

    async def installation_token(self, installation_id: int) -> str:
        cached = self.cache.get(installation_id)
        if cached and cached[1] - 60 > self.clock():
            return cached[0]
        jwt = make_app_jwt(self.app_id, self.private_key, now=int(self.clock()))
        request = self.client.build_request(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {jwt}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": API_VERSION},
        )
        response = await _bounded_send(self.client, request, MAX_TOKEN_RESPONSE_BYTES, "GitHub token")
        data = response.json()
        expiry = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
        self.cache[installation_id] = (data["token"], expiry)
        return data["token"]


class GitHubClient:
    def __init__(self, client: httpx.AsyncClient, token_provider):
        if client.follow_redirects:
            raise ValueError("GitHub client must not follow redirects")
        self.client = client
        self.token_provider = token_provider

    @staticmethod
    def _repo(repo: str) -> str:
        parts = repo.split("/")
        if len(parts) != 2 or not all(part and part.replace("-", "").replace("_", "").replace(".", "").isalnum()
                                         for part in parts):
            raise ValueError("invalid repository name")
        return repo

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        maximum = kwargs.pop("_maximum", MAX_GITHUB_RESPONSE_BYTES)
        token = await self.token_provider()
        request = self.client.build_request(
            method, path, headers={"Authorization": f"Bearer {token}",
                                   "Accept": "application/vnd.github+json",
                                   "X-GitHub-Api-Version": API_VERSION}, timeout=20, **kwargs)
        return await _bounded_send(self.client, request, maximum, "GitHub")

    async def get_pr(self, repo: str, number: int) -> dict:
        response = await self._request("GET", f"/repos/{self._repo(repo)}/pulls/{int(number)}")
        return response.json()

    async def pr_files(self, repo: str, number: int) -> list[dict]:
        result: list[dict] = []
        aggregate_bytes = 0
        for page in range(1, 101):
            try:
                response = await self._request(
                    "GET", f"/repos/{self._repo(repo)}/pulls/{int(number)}/files",
                    params={"per_page": min(100, MAX_PR_FILES - len(result)), "page": page},
                    _maximum=MAX_PR_FILES_BYTES - aggregate_bytes)
            except ValueError as exc:
                if "response too large" in str(exc):
                    raise ReviewTooLarge(
                        "PR file aggregate bytes exceed review limit; analysis is incomplete") from exc
                raise
            aggregate_bytes += len(response.content)
            data = response.json()
            if not isinstance(data, list):
                raise ValueError("invalid GitHub files response")
            for item in data:
                if len(result) >= MAX_PR_FILES:
                    raise ReviewTooLarge("PR file count exceeds review limit; analysis is incomplete")
                result.append(item)
            if 'rel="next"' not in response.headers.get("Link", ""):
                return result
            if len(result) >= MAX_PR_FILES:
                raise ReviewTooLarge("PR file count exceeds review limit; analysis is incomplete")
        raise ValueError("GitHub pagination limit exceeded")

    async def list_reviews(self, repo: str, number: int) -> list[dict]:
        result: list[dict] = []
        for page in range(1, 101):
            response = await self._request("GET", f"/repos/{self._repo(repo)}/pulls/{int(number)}/reviews",
                                           params={"per_page": 100, "page": page})
            data = response.json()
            if not isinstance(data, list):
                raise ValueError("invalid reviews response")
            result.extend(data)
            if 'rel="next"' not in response.headers.get("Link", ""):
                return result
        raise ValueError("GitHub pagination limit exceeded")

    async def check_runs(self, repo: str, sha: str) -> list[dict]:
        result: list[dict] = []
        for page in range(1, 101):
            response = await self._request("GET", f"/repos/{self._repo(repo)}/commits/{sha}/check-runs",
                                           params={"per_page": 100, "page": page})
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("check_runs"), list):
                raise ValueError("invalid check runs response")
            result.extend(data["check_runs"])
            if 'rel="next"' not in response.headers.get("Link", ""):
                return result
        raise ValueError("GitHub pagination limit exceeded")

    async def create_review(self, repo: str, number: int, payload: dict) -> dict:
        return (await self._request("POST", f"/repos/{self._repo(repo)}/pulls/{int(number)}/reviews",
                                    json=payload)).json()

    async def create_check(self, repo: str, payload: dict) -> dict:
        return (await self._request("POST", f"/repos/{self._repo(repo)}/check-runs", json=payload)).json()
