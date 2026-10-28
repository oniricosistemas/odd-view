import json
import hashlib
import uuid

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError

from .store import DeliveryConflict, Store
from .webhook import MAX_BODY_BYTES, WebhookError, verify_webhook

_ALLOWED_ACTIONS = {"opened", "reopened", "synchronize", "ready_for_review", "closed", "converted_to_draft"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Envelope(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class Installation(Envelope):
    id: StrictInt = Field(gt=0)


class Repository(Envelope):
    id: StrictInt = Field(gt=0)
    full_name: str = Field(min_length=3, max_length=200, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class Head(Envelope):
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class Pull(Envelope):
    number: StrictInt = Field(gt=0)
    state: str = Field(min_length=1, max_length=32)
    draft: StrictBool
    head: Head


class PullEvent(Envelope):
    action: str = Field(min_length=1, max_length=64)
    installation: Installation
    repository: Repository
    pull_request: Pull


class InternalHead(Strict):
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class InternalPull(Strict):
    number: StrictInt = Field(gt=0)
    state: str = Field(min_length=1, max_length=32)
    draft: StrictBool
    head: InternalHead


class InternalEvent(Strict):
    action: str = Field(min_length=1, max_length=64)
    installation_id: StrictInt = Field(gt=0)
    repository_id: StrictInt = Field(gt=0)
    repository_full_name: str
    pull: InternalPull


def create_app(store: Store, webhook_secret: bytes, policy_version: str) -> FastAPI:
    app = FastAPI(title="AI Reviewer", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    async def ready() -> dict:
        try:
            with store.connect() as db:
                db.execute("SELECT 1").fetchone()
        except Exception as exc:
            raise HTTPException(503, "database unavailable") from exc
        return {"status": "ready"}

    @app.post("/webhook", status_code=202)
    async def webhook(request: Request) -> dict:
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                raise HTTPException(413, "body too large")
            chunks.append(chunk)
        body = b"".join(chunks)
        try:
            verify_webhook(body, request.headers.get("X-Hub-Signature-256"),
                           request.headers.get("X-GitHub-Event"), webhook_secret)
        except WebhookError as exc:
            raise HTTPException(401 if "signature" in str(exc) else 400, str(exc)) from exc
        try:
            envelope = PullEvent.model_validate(json.loads(body))
            event = InternalEvent.model_validate({
                "action": envelope.action,
                "installation_id": envelope.installation.id,
                "repository_id": envelope.repository.id,
                "repository_full_name": envelope.repository.full_name,
                "pull": envelope.pull_request.model_dump(),
            })
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(422, "invalid payload") from exc
        delivery = request.headers.get("X-GitHub-Delivery")
        if not delivery:
            raise HTTPException(400, "missing delivery id")
        try:
            delivery = str(uuid.UUID(delivery))
        except ValueError as exc:
            raise HTTPException(400, "invalid delivery id") from exc
        if event.action not in _ALLOWED_ACTIONS:
            return {"ignored": event.action}
        pull = event.pull
        try:
            # Webhooks are hints only. Live PR state is authoritative in the worker.
            run_id = store.ingest(delivery, event.repository_id, pull.number, pull.head.sha,
                                  policy_version, event.installation_id, event.repository_full_name,
                                  body_hash=hashlib.sha256(body).hexdigest(), action=event.action)
        except DeliveryConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"run_id": run_id}

    return app
