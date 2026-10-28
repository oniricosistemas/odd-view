import hashlib
import hmac

MAX_BODY_BYTES = 1024 * 1024
_ALLOWED_EVENTS = {"pull_request"}


class WebhookError(ValueError):
    pass


def verify_webhook(body: bytes, signature: str | None, event: str | None, secret: bytes) -> None:
    if len(body) > MAX_BODY_BYTES:
        raise WebhookError("body too large")
    if event not in _ALLOWED_EVENTS:
        raise WebhookError("event not allowed")
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if signature is None or not hmac.compare_digest(signature, expected):
        raise WebhookError("invalid signature")
