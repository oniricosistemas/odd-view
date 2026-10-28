import hashlib
import hmac

import pytest

from ai_reviewer.webhook import MAX_BODY_BYTES, WebhookError, verify_webhook


def test_webhook_verifies_raw_body_hmac_and_allowlist():
    body = b'{"action":"opened"}'
    signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    verify_webhook(body, signature, "pull_request", b"secret")
    with pytest.raises(WebhookError):
        verify_webhook(body + b" ", signature, "pull_request", b"secret")
    with pytest.raises(WebhookError):
        verify_webhook(body, signature, "push", b"secret")


def test_webhook_rejects_body_over_one_mib_before_parsing():
    with pytest.raises(WebhookError, match="too large"):
        verify_webhook(b"x" * (MAX_BODY_BYTES + 1), "sha256=bad", "pull_request", b"secret")
