import concurrent.futures
import json

import pytest

from ai_reviewer.store import DeliveryConflict, LeaseLost, Store


def test_delivery_and_run_dedup_and_new_sha_does_not_cancel_by_webhook_order(tmp_path):
    store = Store(tmp_path / "state.db")
    first = store.ingest("delivery-1", 7, 12, "a" * 40, "v1", 99, body_hash="a" * 64)
    assert store.ingest("delivery-1", 7, 12, "a" * 40, "v1", 99, body_hash="a" * 64) == first
    with pytest.raises(DeliveryConflict):
        store.ingest("delivery-1", 7, 12, "b" * 40, "v1", 99, body_hash="b" * 64)
    assert store.ingest("delivery-2", 7, 12, "a" * 40, "v1", 99, body_hash="a" * 64) == first
    second = store.ingest("delivery-3", 7, 12, "b" * 40, "v1", 99, body_hash="b" * 64)
    assert second != first
    assert store.get_run(first)["status"] == "queued"


def test_lease_is_single_owner_and_can_be_reclaimed(tmp_path):
    store = Store(tmp_path / "state.db")
    with pytest.raises(ValueError, match="SHA"):
        store.ingest("bad", 1, 2, "sha", "v1", 3)
    run = store.ingest("d", 1, 2, "a" * 40, "v1", 3)
    assert store.claim("worker-a", now=10, lease_seconds=5)["id"] == run
    assert store.claim("worker-b", now=12, lease_seconds=5) is None
    reclaimed = store.claim("worker-b", now=16, lease_seconds=5)
    assert reclaimed["id"] == run and reclaimed["lease_generation"] == 2


def test_lease_heartbeat_fencing_and_bounded_retry(tmp_path):
    store = Store(tmp_path / "state.db")
    run_id = store.ingest("d", 1, 2, "a" * 40, "v1", 3)
    run = store.claim("a", now=10, lease_seconds=5)
    assert store.heartbeat(run_id, "a", run["lease_generation"], now=12, lease_seconds=5)
    assert store.claim("b", now=16, lease_seconds=5) is None
    with pytest.raises(LeaseLost):
        store.update_owned(run_id, "wrong", run["lease_generation"], status="completed")
    assert store.fail_and_retry(run_id, "a", run["lease_generation"], now=14, max_attempts=2)
    assert store.claim("b", now=15) is None
    retried = store.claim("b", now=16)
    assert retried is not None and retried["attempts"] == 2
    assert not store.fail_and_retry(run_id, "b", retried["lease_generation"], now=30, max_attempts=2)
    assert store.get_run(run_id)["status"] == "failed"


def test_publication_lock_is_fenced_and_durable(tmp_path):
    store = Store(tmp_path / "state.db")
    run_id = store.ingest("d", 1, 2, "a" * 40, "v1", 3)
    run = store.claim("a", now=1)
    assert store.acquire_publication(run_id, "a", run["lease_generation"], now=2)
    assert not store.acquire_publication(run_id, "b", run["lease_generation"], now=2)
    store.record_publication(run_id, "a", run["lease_generation"], review_id=10, now=2)
    assert store.get_run(run_id)["review_id"] == 10
    store.cancel_owned(run_id, "a", run["lease_generation"], now=2)
    cancelled = store.get_run(run_id)
    assert cancelled["status"] == "cancelled" and cancelled["residual_race"] == 1


def test_expired_lease_cannot_mutate_or_acquire_publication_before_reclaim(tmp_path):
    store = Store(tmp_path / "state.db")
    run_id = store.ingest("d", 1, 2, "a" * 40, "v1", 3)
    run = store.claim("a", now=10, lease_seconds=5)
    with pytest.raises(LeaseLost):
        store.update_owned(run_id, "a", run["lease_generation"], now=16, result_json="[]")
    assert not store.acquire_publication(run_id, "a", run["lease_generation"], now=16)
    with pytest.raises(LeaseLost):
        store.fail_and_retry(run_id, "a", run["lease_generation"], now=16)


def test_publication_cas_snapshot_is_immutable_under_real_sqlite_concurrency(tmp_path):
    store = Store(tmp_path / "state.db")
    run_id = store.ingest("d", 1, 2, "a" * 40, "v1", 3)
    run = store.claim("worker", now=10, lease_seconds=100)
    snapshot = json.dumps({"review": {"event": "COMMENT"}, "check": {"name": "AI Review"}}, sort_keys=True)

    def race(owner):
        return store.acquire_publication(run_id, "worker", run["lease_generation"],
                                         publication_owner=owner, snapshot_json=snapshot,
                                         now=11, lock_seconds=30)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, ("publisher-a", "publisher-b")))
    assert sum(result is not None for result in results) == 1
    winner = next(result for result in results if result is not None)
    assert winner["snapshot_json"] == snapshot
    assert store.acquire_publication(run_id, "worker", run["lease_generation"],
                                     publication_owner="loser", snapshot_json="{}",
                                     now=12, lock_seconds=30) is None
    with pytest.raises(ValueError, match="immutable"):
        store.acquire_publication(run_id, "worker", run["lease_generation"],
                                  publication_owner=winner["owner"], snapshot_json="{}",
                                  now=12, lock_seconds=30)


def test_expired_publication_lock_takeover_increments_generation_and_keeps_snapshot(tmp_path):
    store = Store(tmp_path / "state.db")
    run_id = store.ingest("d", 1, 2, "a" * 40, "v1", 3)
    run = store.claim("worker", now=10, lease_seconds=100)
    first = store.acquire_publication(run_id, "worker", run["lease_generation"],
                                      publication_owner="p1", snapshot_json='{"fixed":true}',
                                      now=11, lock_seconds=2)
    assert first["generation"] == 1
    second = store.acquire_publication(run_id, "worker", run["lease_generation"],
                                       publication_owner="p2", snapshot_json='{"fixed":true}',
                                       now=14, lock_seconds=2)
    assert second["generation"] == 2 and second["snapshot_json"] == first["snapshot_json"]
    assert not store.heartbeat_publication(run_id, "worker", run["lease_generation"],
                                           "p1", first["generation"], now=14)
    assert store.heartbeat_publication(run_id, "worker", run["lease_generation"],
                                       "p2", second["generation"], now=14)


def test_cancelled_and_failed_runs_reactivate_only_for_legitimate_actions(tmp_path):
    store = Store(tmp_path / "state.db")
    run_id = store.ingest("d1", 1, 2, "a" * 40, "v1", 3)
    run = store.claim("w", now=1, lease_seconds=10)
    store.cancel_owned(run_id, "w", run["lease_generation"], now=2)
    assert store.ingest("d2", 1, 2, "a" * 40, "v1", 3, action="synchronize", now=3) == run_id
    assert store.get_run(run_id)["status"] == "cancelled"
    store.ingest("d3", 1, 2, "a" * 40, "v1", 3, action="ready_for_review", now=3)
    assert store.get_run(run_id)["status"] == "queued"

    claimed = store.claim("w", now=3, lease_seconds=10)
    assert not store.fail_and_retry(run_id, "w", claimed["lease_generation"], now=4, max_attempts=2)
    assert store.get_run(run_id)["status"] == "failed"
    store.ingest("d4", 1, 2, "a" * 40, "v1", 3, action="synchronize", now=5, max_attempts=3)
    failed = store.get_run(run_id)
    assert failed["status"] == "queued" and failed["next_attempt"] > 5


def test_expired_poison_run_is_terminal_at_attempt_budget_and_next_run_is_claimed(tmp_path):
    store = Store(tmp_path / "state.db")
    poison = store.ingest("poison", 1, 1, "a" * 40, "v1", 3)
    healthy = store.ingest("healthy", 1, 2, "b" * 40, "v1", 3)
    now = 0
    for attempt in range(7):
        claimed = store.claim(f"crash-{attempt}", now=now, lease_seconds=1, max_attempts=7)
        assert claimed["id"] == poison
        now += 2
    claimed = store.claim("survivor", now=now, lease_seconds=10, max_attempts=7)
    assert store.get_run(poison)["status"] == "failed"
    assert claimed["id"] == healthy


def test_reopened_after_exhaustion_starts_auditable_new_execution_but_completed_does_not(tmp_path):
    store = Store(tmp_path / "state.db")
    run_id = store.ingest("d1", 1, 2, "a" * 40, "v1", 3)
    run = store.claim("w", now=1, max_attempts=1)
    store.fail_and_retry(run_id, "w", run["lease_generation"], now=2, max_attempts=1)
    store.ingest("d2", 1, 2, "a" * 40, "v1", 9, "renamed/repo", action="reopened", now=3,
                 max_attempts=1)
    restarted = store.get_run(run_id)
    assert restarted["status"] == "queued" and restarted["attempts"] == 0
    assert restarted["execution_generation"] == 2
    assert restarted["reactivation_action"] == "reopened" and restarted["reactivated_at"] == 3
    claimed = store.claim("w", now=3)
    store.update_owned(run_id, "w", claimed["lease_generation"], now=3, status="completed")
    store.ingest("d3", 1, 2, "a" * 40, "v1", 9, "renamed/repo", action="ready_for_review", now=4)
    assert store.get_run(run_id)["status"] == "completed"


def test_deduped_metadata_is_pending_until_live_confirmation(tmp_path):
    store = Store(tmp_path / "state.db")
    run_id = store.ingest("d1", 7, 2, "a" * 40, "v1", 3, "old/repo")
    store.ingest("d2", 7, 2, "a" * 40, "v1", 9, "new/repo", action="synchronize")
    pending = store.get_run(run_id)
    assert pending["installation_id"] == 3 and pending["repository_full_name"] == "old/repo"
    assert pending["pending_installation_id"] == 9
    assert pending["pending_repository_full_name"] == "new/repo"
    claimed = store.claim("worker", now=1, lease_seconds=10)
    store.confirm_metadata(run_id, "worker", claimed["lease_generation"], 9, "new/repo", now=2)
    confirmed = store.get_run(run_id)
    assert confirmed["installation_id"] == 9 and confirmed["repository_full_name"] == "new/repo"
    assert confirmed["pending_installation_id"] is None
