import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ai_reviewer.config import load_settings


def pem_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def test_configuration_uses_file_env_overrides_and_secret_files(tmp_path):
    secret = tmp_path / "webhook"; secret.write_text("h" * 32 + "\n")
    key = tmp_path / "key"; key.write_bytes(pem_key())
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"app_id": 12, "review_author_id": 34,
        "database_path": "/var/lib/ai-reviewer/state.db",
        "omniroute_base_url": "http://192.168.1.192:20128/v1", "allow_insecure_omniroute": True}))
    settings = load_settings({"AI_REVIEWER_CONFIG": str(config),
        "AI_REVIEWER_WEBHOOK_SECRET_FILE": str(secret), "AI_REVIEWER_APP_PRIVATE_KEY_FILE": str(key),
        "AI_REVIEWER_PORT": "9000"})
    assert settings.host == "127.0.0.1" and settings.port == 9000
    assert settings.webhook_secret == b"h" * 32
    assert b"PRIVATE KEY" in settings.app_private_key


def test_inline_secrets_are_not_configuration_fields():
    with pytest.raises(ValueError):
        load_settings({"AI_REVIEWER_WEBHOOK_SECRET": "forbidden"})


def test_config_rejects_insecure_remote_and_non_loopback_defaults(tmp_path):
    secret = tmp_path / "secret"; secret.write_text("x" * 32)
    key = tmp_path / "key"; key.write_bytes(pem_key())
    base = {"AI_REVIEWER_WEBHOOK_SECRET_FILE": str(secret),
            "AI_REVIEWER_APP_PRIVATE_KEY_FILE": str(key)}
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"app_id": 1, "review_author_id": 2, "database_path": "state.db",
                                  "omniroute_base_url": "http://router.lan/v1"}))
    with pytest.raises(ValueError, match="HTTPS"):
        load_settings({**base, "AI_REVIEWER_CONFIG": str(config)})
    config.write_text(json.dumps({"app_id": 1, "review_author_id": 2, "database_path": "state.db",
                                  "omniroute_base_url": "https://router.example/v1", "host": "0.0.0.0"}))
    with pytest.raises(ValueError, match="loopback"):
        load_settings({**base, "AI_REVIEWER_CONFIG": str(config)})


def test_config_rejects_weak_secrets_invalid_pem_and_coerced_integers(tmp_path):
    secret = tmp_path / "secret"; secret.write_text("   ")
    key = tmp_path / "key"; key.write_text("not pem")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"app_id": "1", "review_author_id": 2, "database_path": "state.db",
                                  "omniroute_base_url": "https://router.example/v1"}))
    with pytest.raises(ValueError):
        load_settings({"AI_REVIEWER_CONFIG": str(config), "AI_REVIEWER_WEBHOOK_SECRET_FILE": str(secret),
                       "AI_REVIEWER_APP_PRIVATE_KEY_FILE": str(key)})


def test_config_file_rejects_inline_secret_fields_for_every_role(tmp_path):
    secret = tmp_path / "secret"; secret.write_text("x" * 32)
    key = tmp_path / "key"; key.write_bytes(pem_key())
    base = {"app_id": 1, "review_author_id": 2, "database_path": "state.db",
            "omniroute_base_url": "https://router.example/v1"}
    for field in ("webhook_secret", "app_private_key", "marker_secret", "omniroute_api_key"):
        config = tmp_path / f"{field}.json"
        config.write_text(json.dumps({**base, field: "inline-forbidden-value"}))
        with pytest.raises(ValueError, match="inline secret"):
            load_settings({"AI_REVIEWER_CONFIG": str(config),
                           "AI_REVIEWER_WEBHOOK_SECRET_FILE": str(secret)}, role="api")


def test_role_loaders_require_only_their_own_credentials_and_reject_whitespace(tmp_path):
    secret = tmp_path / "secret"; secret.write_text(" " + "x" * 32)
    key = tmp_path / "key"; key.write_bytes(pem_key())
    marker = tmp_path / "marker"; marker.write_text("m" * 32)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"app_id": 1, "review_author_id": 2, "database_path": "state.db",
                                  "omniroute_base_url": "https://router.example/v1"}))
    with pytest.raises(ValueError, match="whitespace"):
        load_settings({"AI_REVIEWER_CONFIG": str(config),
                       "AI_REVIEWER_WEBHOOK_SECRET_FILE": str(secret)}, role="api")
    worker = load_settings({"AI_REVIEWER_CONFIG": str(config),
                            "AI_REVIEWER_APP_PRIVATE_KEY_FILE": str(key),
                            "AI_REVIEWER_MARKER_SECRET_FILE": str(marker)}, role="worker")
    assert worker.webhook_secret is None and worker.omniroute_api_key is None
    omni_key = tmp_path / "omni"; omni_key.write_text(" " + "k" * 32 + "\n")
    with pytest.raises(ValueError, match="whitespace"):
        load_settings({"AI_REVIEWER_CONFIG": str(config),
                       "AI_REVIEWER_APP_PRIVATE_KEY_FILE": str(key),
                       "AI_REVIEWER_MARKER_SECRET_FILE": str(marker),
                       "AI_REVIEWER_OMNIROUTE_API_KEY_FILE": str(omni_key)}, role="worker")
    with pytest.raises(ValueError, match="not permitted for api"):
        load_settings({"AI_REVIEWER_CONFIG": str(config),
                       "AI_REVIEWER_WEBHOOK_SECRET_FILE": str(secret),
                       "AI_REVIEWER_APP_PRIVATE_KEY_FILE": str(key)}, role="api")
    clean_secret = tmp_path / "clean-secret"; clean_secret.write_text("s" * 32)
    with pytest.raises(ValueError, match="not permitted for worker"):
        load_settings({"AI_REVIEWER_CONFIG": str(config),
                       "AI_REVIEWER_APP_PRIVATE_KEY_FILE": str(key),
                       "AI_REVIEWER_MARKER_SECRET_FILE": str(marker),
                       "AI_REVIEWER_WEBHOOK_SECRET_FILE": str(clean_secret)}, role="worker")
