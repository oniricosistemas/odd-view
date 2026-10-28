import json
import os
import ipaddress
from pathlib import Path
from typing import Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, StrictInt, field_validator, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    app_id: StrictInt = Field(gt=0)
    review_author_id: StrictInt = Field(gt=0)
    database_path: str
    omniroute_base_url: HttpUrl
    allow_insecure_omniroute: StrictBool = False
    policy_version: str = "v1"
    host: str = "127.0.0.1"
    port: StrictInt = Field(default=8080, ge=1, le=65535)
    allow_remote_api: StrictBool = False
    webhook_secret: bytes | None = Field(default=None, min_length=32)
    app_private_key: bytes | None = None
    marker_secret: bytes | None = Field(default=None, min_length=32)
    omniroute_api_key: str | None = None

    @field_validator("webhook_secret", "marker_secret")
    @classmethod
    def strong_unpadded_secret(cls, value: bytes | None) -> bytes | None:
        if value is not None and value != value.strip():
            raise ValueError("secret must not contain surrounding whitespace")
        return value

    @field_validator("app_private_key")
    @classmethod
    def valid_rsa_pem(cls, value: bytes | None) -> bytes | None:
        if value is None:
            return value
        try:
            key = serialization.load_pem_private_key(value, password=None)
        except (TypeError, ValueError) as exc:
            raise ValueError("app_private_key must be an unencrypted PEM RSA private key") from exc
        if not isinstance(key, RSAPrivateKey):
            raise ValueError("app_private_key must be RSA")
        if key.key_size < 2048:
            raise ValueError("app_private_key must be at least 2048 bits")
        return value

    @model_validator(mode="after")
    def secure_network_defaults(self):
        if self.omniroute_base_url.scheme != "https" and not self.allow_insecure_omniroute:
            raise ValueError("remote OmniRoute must use HTTPS unless allow_insecure_omniroute=true")
        try:
            loopback = ipaddress.ip_address(self.host).is_loopback
        except ValueError:
            loopback = self.host == "localhost"
        if not loopback and not self.allow_remote_api:
            raise ValueError("API host must be loopback unless allow_remote_api=true")
        return self


def _read_secret(path: str, binary: bool = True):
    data = Path(path).read_bytes().rstrip(b"\r\n")
    return data if binary else data.decode()


def load_settings(environ: Mapping[str, str] | None = None, role: str | None = None) -> Settings:
    env = dict(os.environ if environ is None else environ)
    forbidden = {"AI_REVIEWER_WEBHOOK_SECRET", "AI_REVIEWER_APP_PRIVATE_KEY",
                 "AI_REVIEWER_OMNIROUTE_API_KEY", "AI_REVIEWER_MARKER_SECRET"}
    if forbidden & env.keys():
        raise ValueError("secrets must use *_FILE")
    values: dict = {}
    config_path = env.get("AI_REVIEWER_CONFIG")
    if config_path:
        loaded = json.loads(Path(config_path).read_text())
        if not isinstance(loaded, dict):
            raise ValueError("configuration must be an object")
        inline_secrets = {"webhook_secret", "app_private_key", "marker_secret", "omniroute_api_key"}
        if inline_secrets & loaded.keys():
            raise ValueError("inline secret fields are forbidden")
        values.update(loaded)
    names = {"APP_ID": "app_id", "REVIEW_AUTHOR_ID": "review_author_id", "DATABASE_PATH": "database_path",
             "OMNIROUTE_BASE_URL": "omniroute_base_url", "POLICY_VERSION": "policy_version",
             "HOST": "host", "PORT": "port", "ALLOW_INSECURE_OMNIROUTE": "allow_insecure_omniroute",
             "ALLOW_REMOTE_API": "allow_remote_api"}
    for suffix, field in names.items():
        if f"AI_REVIEWER_{suffix}" in env:
            raw = env[f"AI_REVIEWER_{suffix}"]
            if field in {"app_id", "review_author_id", "port"}:
                try:
                    raw = int(raw)
                except ValueError as exc:
                    raise ValueError(f"{field} must be an integer") from exc
            elif field in {"allow_insecure_omniroute", "allow_remote_api"}:
                if raw not in {"true", "false"}:
                    raise ValueError(f"{field} must be true or false")
                raw = raw == "true"
            values[field] = raw
    if role not in {None, "api", "worker"}:
        raise ValueError("invalid role")
    role_forbidden = {
        "api": {"AI_REVIEWER_APP_PRIVATE_KEY_FILE", "AI_REVIEWER_MARKER_SECRET_FILE",
                "AI_REVIEWER_OMNIROUTE_API_KEY_FILE"},
        "worker": {"AI_REVIEWER_WEBHOOK_SECRET_FILE"},
    }
    if role is not None:
        present_forbidden = role_forbidden[role] & env.keys()
        if present_forbidden:
            raise ValueError(f"credential is not permitted for {role} role")
    required_files = ({"AI_REVIEWER_WEBHOOK_SECRET_FILE": "webhook_secret"} if role == "api" else
                      {"AI_REVIEWER_APP_PRIVATE_KEY_FILE": "app_private_key",
                       "AI_REVIEWER_MARKER_SECRET_FILE": "marker_secret"} if role == "worker" else
                      {"AI_REVIEWER_WEBHOOK_SECRET_FILE": "webhook_secret",
                       "AI_REVIEWER_APP_PRIVATE_KEY_FILE": "app_private_key"})
    for variable, field in required_files.items():
        if variable not in env:
            raise ValueError(f"missing {variable}")
        values[field] = _read_secret(env[variable])
    key_file = env.get("AI_REVIEWER_OMNIROUTE_API_KEY_FILE") if role != "api" else None
    if key_file:
        api_key = _read_secret(key_file, binary=False)
        if api_key != api_key.strip():
            raise ValueError("OmniRoute API key must not contain surrounding whitespace")
        if len(api_key) < 32:
            raise ValueError("OmniRoute API key must contain at least 32 characters")
        values["omniroute_api_key"] = api_key
    return Settings.model_validate(values)
