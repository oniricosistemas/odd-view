import hashlib
import hmac
import json
import uuid

from fastapi.testclient import TestClient

from ai_reviewer.api import create_app
from ai_reviewer.store import Store


def signed(client, body, delivery=None):
    delivery = delivery or str(uuid.uuid4())
    signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    return client.post("/webhook", content=body, headers={"X-Hub-Signature-256": signature,
        "X-GitHub-Event": "pull_request", "X-GitHub-Delivery": delivery,
        "Content-Type": "application/json"})


def payload(draft=False, action="opened", sha=None):
    sha = sha or "a" * 40
    return __import__("json").dumps({"action": action, "installation": {"id": 9},
        "repository": {"id": 1, "full_name": "o/r"},
        "pull_request": {"number": 2, "state": "open", "draft": draft, "head": {"sha": sha}}}).encode()


def test_health_readiness_and_webhook_ingestion_cancellation(tmp_path):
    store = Store(tmp_path / "db")
    with TestClient(create_app(store, b"secret", "v1")) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/readyz").status_code == 200
        response = signed(client, payload())
        assert response.status_code == 202
        run = response.json()["run_id"]
        assert signed(client, payload(draft=True, action="synchronize")).status_code == 202
        assert store.get_run(run)["status"] == "queued"


def test_webhook_accepts_representative_github_extra_properties(tmp_path):
    store = Store(tmp_path / "db")
    data = json.loads(payload())
    data["sender"] = {"login": "octocat", "avatar_url": "https://example.invalid/a.png"}
    data["repository"].update({"private": True, "owner": {"login": "o"}})
    data["pull_request"].update({"html_url": "https://github.com/o/r/pull/2", "user": {"id": 1}})
    data["pull_request"]["head"].update({"ref": "feature", "repo": {"id": 1}})
    body = json.dumps(data).encode()
    with TestClient(create_app(store, b"secret", "v1")) as client:
        assert signed(client, body).status_code == 202


def test_delivery_requires_uuid_and_same_uuid_different_body_is_incident(tmp_path):
    store = Store(tmp_path / "db")
    delivery = str(uuid.uuid4())
    with TestClient(create_app(store, b"secret", "v1")) as client:
        assert signed(client, payload(), "not-a-uuid").status_code == 400
        assert signed(client, payload(), delivery).status_code == 202
        response = signed(client, payload(sha="b" * 40), delivery)
        assert response.status_code == 409
        assert response.json()["detail"] == "delivery body mismatch"


def test_delivery_uuid_is_canonicalized_before_persistence(tmp_path):
    store = Store(tmp_path / "db")
    delivery = str(uuid.uuid4())
    with TestClient(create_app(store, b"secret", "v1")) as client:
        first = signed(client, payload(), delivery.upper())
        second = signed(client, payload(), delivery.lower())
    assert first.status_code == second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM deliveries").fetchone()[0] == 1
