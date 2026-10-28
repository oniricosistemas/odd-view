import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from ai_reviewer.github import GitHubAuth, make_app_jwt


def private_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def decode_part(token, part):
    raw = token.split(".")[part]
    return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def test_app_jwt_has_short_lived_expected_claims():
    token = make_app_jwt("123", private_key(), now=1000)
    claims = decode_part(token, 1)
    assert claims == {"iat": 940, "exp": 1540, "iss": "123"}


@pytest.mark.asyncio
async def test_installation_token_is_cached_until_expiry():
    calls = 0
    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(201, json={"token": "installation", "expires_at": "2030-01-01T00:00:00Z"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        auth = GitHubAuth("123", private_key(), client, clock=lambda: 1000)
        assert await auth.installation_token(9) == "installation"
        assert await auth.installation_token(9) == "installation"
    assert calls == 1


@pytest.mark.asyncio
async def test_installation_token_response_is_stream_bounded():
    consumed = 0
    class Huge(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal consumed
            for _ in range(20):
                consumed += 1
                yield b"x" * (64 * 1024)
    async def handler(request):
        return httpx.Response(201, stream=Huge())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        with pytest.raises(ValueError, match="too large"):
            await GitHubAuth("123", private_key(), client, clock=lambda: 1000).installation_token(9)
    assert consumed <= 5
