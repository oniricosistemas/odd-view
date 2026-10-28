import asyncio
import json
import logging
import sys
import uuid

import httpx
import uvicorn

from .api import create_app
from .config import load_settings
from .github import GitHubAuth, GitHubClient
from .omniroute import OmniRouteClient
from .store import Store
from .worker import Worker

logger = logging.getLogger("ai_reviewer.worker")


def log_worker_failure(run_id: int, generation: int, exc: Exception) -> None:
    logger.error(json.dumps({"code": "worker_run_failed", "error_class": type(exc).__name__,
                             "generation": generation, "run_id": run_id}, sort_keys=True,
                            separators=(",", ":")))


async def run_worker() -> None:
    settings = load_settings(role="worker")
    store = Store(settings.database_path)
    timeout = httpx.Timeout(20, connect=5)
    async with httpx.AsyncClient(base_url="https://api.github.com", follow_redirects=False,
                                 timeout=timeout) as github_http, \
               httpx.AsyncClient(base_url=str(settings.omniroute_base_url), follow_redirects=False,
                                 timeout=httpx.Timeout(60, connect=5)) as omni_http:
        assert settings.app_private_key is not None and settings.marker_secret is not None
        auth = GitHubAuth(str(settings.app_id), settings.app_private_key, github_http)
        omni = OmniRouteClient(omni_http, settings.omniroute_api_key)
        owner = str(uuid.uuid4())
        while True:
            run = store.claim(owner, lease_seconds=300)
            if run is None:
                await asyncio.sleep(2)
                continue

            async def token(installation_id=(run["pending_installation_id"]
                                              or run["installation_id"])):
                return await auth.installation_token(installation_id)

            github = GitHubClient(github_http, token)
            try:
                await Worker(store, github, omni, settings.marker_secret,
                             settings.review_author_id, settings.app_id).process(
                    run["id"], owner, run["lease_generation"], lease_seconds=300)
            except Exception as exc:
                # Never log exception text: provider errors can contain prompts, diffs, or credentials.
                log_worker_failure(int(run["id"]), int(run["lease_generation"]), exc)
                raise


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"api", "worker"}:
        raise SystemExit("usage: python -m ai_reviewer.main {api|worker}")
    if sys.argv[1] == "worker":
        asyncio.run(run_worker())
    else:
        settings = load_settings(role="api")
        assert settings.webhook_secret is not None
        app = create_app(Store(settings.database_path), settings.webhook_secret, settings.policy_version)
        uvicorn.run(app, host=settings.host, port=settings.port, access_log=False)


if __name__ == "__main__":
    main()
