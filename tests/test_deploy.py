from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_api_and_worker_units_are_separate_least_credential_services():
    api = (ROOT / "deploy/ai-reviewer-api.service").read_text()
    worker = (ROOT / "deploy/ai-reviewer-worker.service").read_text()
    assert "ai_reviewer.main api" in api
    assert "webhook-secret" in api
    assert "app-private-key" not in api and "omniroute-api-key" not in api
    assert "ai_reviewer.main worker" in worker
    assert "app-private-key" in worker and "marker-secret" in worker
    assert "webhook-secret" not in worker and "omniroute-api-key" not in worker
    assert "/etc/a..." not in api + worker
    for unit in (api, worker):
        assert "NoNewPrivileges=true" in unit
        assert "ProtectSystem=strict" in unit
        assert "ProtectProc=invisible" in unit
        assert "ProcSubset=pid" in unit
        assert "RestrictSUIDSGID=true" in unit
        assert "SystemCallArchitectures=native" in unit
        assert "MemoryMax=" in unit and "CPUQuota=" in unit and "TasksMax=" in unit


def test_units_use_distinct_users_and_shared_database_group_without_shared_credentials():
    api = (ROOT / "deploy/ai-reviewer-api.service").read_text()
    worker = (ROOT / "deploy/ai-reviewer-worker.service").read_text()
    assert "User=ai-reviewer-api" in api and "User=ai-reviewer-worker" in worker
    assert "Group=ai-reviewer-state" in api and "Group=ai-reviewer-state" in worker
    assert "StateDirectoryMode=0770" in api and "StateDirectoryMode=0770" in worker
    assert "UMask=0007" in api and "UMask=0007" in worker


def test_readme_uses_real_credential_path_and_https_default():
    readme = (ROOT / "README.md").read_text()
    example = (ROOT / "deploy/config.example.json").read_text()
    assert "/etc/a...-key" not in readme
    assert "/etc/ai-reviewer/credentials/omniroute-api-key" in readme
    assert '"omniroute_base_url": "https://' in example
    assert '"allow_insecure_omniroute": false' in example
