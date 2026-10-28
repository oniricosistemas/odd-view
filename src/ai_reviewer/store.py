import sqlite3
import time
import re
from pathlib import Path


class DeliveryConflict(RuntimeError):
    pass


class LeaseLost(RuntimeError):
    pass


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self) -> None:
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
              id INTEGER PRIMARY KEY, repository_id INTEGER NOT NULL,
              pull_number INTEGER NOT NULL, head_sha TEXT NOT NULL,
              policy_version TEXT NOT NULL, installation_id INTEGER NOT NULL,
              repository_full_name TEXT NOT NULL DEFAULT '',
              pending_installation_id INTEGER, pending_repository_full_name TEXT,
              status TEXT NOT NULL DEFAULT 'queued', lease_owner TEXT,
              lease_until REAL, lease_generation INTEGER NOT NULL DEFAULT 0,
              attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
              execution_generation INTEGER NOT NULL DEFAULT 1,
              reactivation_action TEXT, reactivated_at REAL,
              publication_owner TEXT, publication_generation INTEGER NOT NULL DEFAULT 0,
              publication_until REAL, snapshot_json TEXT,
              residual_race INTEGER NOT NULL DEFAULT 0,
              ambiguity_kind TEXT, ambiguous_since REAL, ambiguous_updated REAL,
              ambiguity_attempts INTEGER NOT NULL DEFAULT 0,
              result_json TEXT, review_id INTEGER, check_id INTEGER,
              UNIQUE(repository_id,pull_number,head_sha,policy_version));
            CREATE TABLE IF NOT EXISTS deliveries (
              delivery_id TEXT PRIMARY KEY, body_hash TEXT NOT NULL,
              run_id INTEGER NOT NULL REFERENCES runs(id));
            """)
            run_columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
            migrations = {
                "lease_generation": "INTEGER NOT NULL DEFAULT 0",
                "pending_installation_id": "INTEGER",
                "pending_repository_full_name": "TEXT",
                "attempts": "INTEGER NOT NULL DEFAULT 0",
                "next_attempt": "REAL NOT NULL DEFAULT 0",
                "execution_generation": "INTEGER NOT NULL DEFAULT 1",
                "reactivation_action": "TEXT",
                "reactivated_at": "REAL",
                "publication_owner": "TEXT",
                "publication_generation": "INTEGER NOT NULL DEFAULT 0",
                "publication_until": "REAL",
                "snapshot_json": "TEXT",
                "residual_race": "INTEGER NOT NULL DEFAULT 0",
                "ambiguity_kind": "TEXT",
                "ambiguous_since": "REAL",
                "ambiguous_updated": "REAL",
                "ambiguity_attempts": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, declaration in migrations.items():
                if name not in run_columns:
                    db.execute(f"ALTER TABLE runs ADD COLUMN {name} {declaration}")
            delivery_columns = {row[1] for row in db.execute("PRAGMA table_info(deliveries)")}
            if "body_hash" not in delivery_columns:
                db.execute("ALTER TABLE deliveries ADD COLUMN body_hash TEXT NOT NULL DEFAULT ''")

    def ingest(self, delivery_id: str, repository_id: int, pull_number: int,
               head_sha: str, policy_version: str, installation_id: int,
               repository_full_name: str = "", body_hash: str = "", *,
               action: str | None = None, now: float | None = None,
               max_attempts: int = 3) -> int:
        if re.fullmatch(r"[0-9a-f]{40}", head_sha) is None:
            raise ValueError("head SHA must be exactly 40 lowercase hexadecimal characters")
        if body_hash and re.fullmatch(r"[0-9a-f]{64}", body_hash) is None:
            raise ValueError("body hash must be exactly 64 lowercase hexadecimal characters")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT run_id,body_hash FROM deliveries WHERE delivery_id=?", (delivery_id,)).fetchone()
            if row:
                if row["body_hash"] != body_hash:
                    db.rollback()
                    raise DeliveryConflict("delivery body mismatch")
                db.commit()
                return int(row[0])
            db.execute("""INSERT OR IGNORE INTO runs(repository_id,pull_number,head_sha,policy_version,installation_id,
                       repository_full_name) VALUES(?,?,?,?,?,?)""",
                       (repository_id, pull_number, head_sha, policy_version, installation_id, repository_full_name))
            run = db.execute("""SELECT id FROM runs WHERE repository_id=? AND pull_number=?
                              AND head_sha=? AND policy_version=?""",
                             (repository_id, pull_number, head_sha, policy_version)).fetchone()
            run_id = int(run[0])
            if action in {"opened", "reopened", "synchronize", "ready_for_review"}:
                db.execute("""UPDATE runs SET pending_installation_id=?,pending_repository_full_name=?
                           WHERE id=?""", (installation_id, repository_full_name, run_id))
                current = db.execute("SELECT status,attempts FROM runs WHERE id=?", (run_id,)).fetchone()
                if current["status"] == "cancelled" and action in {"reopened", "ready_for_review"}:
                    db.execute("""UPDATE runs SET status='queued',next_attempt=?,lease_owner=NULL,
                               lease_until=NULL WHERE id=? AND status='cancelled'""",
                               (0 if now is None else now, run_id))
                elif current["status"] == "failed" and int(current["attempts"]) < max_attempts:
                    at = time.time() if now is None else now
                    delay = min(300, 2 ** int(current["attempts"]))
                    db.execute("""UPDATE runs SET status='queued',next_attempt=?,lease_owner=NULL,
                               lease_until=NULL WHERE id=? AND status='failed'""", (at + delay, run_id))
                elif (current["status"] == "failed" and int(current["attempts"]) >= max_attempts
                      and action in {"reopened", "ready_for_review"}):
                    at = time.time() if now is None else now
                    db.execute("""UPDATE runs SET status='queued',attempts=0,next_attempt=?,lease_owner=NULL,
                               lease_until=NULL,execution_generation=execution_generation+1,
                               reactivation_action=?,reactivated_at=? WHERE id=? AND status='failed'""",
                               (at, action, at, run_id))
            db.execute("INSERT INTO deliveries(delivery_id,body_hash,run_id) VALUES(?,?,?)",
                       (delivery_id, body_hash, run_id))
            db.commit()
            return run_id

    def get_run(self, run_id: int) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            return dict(row)

    def claim(self, owner: str, *, now: float | None = None, lease_seconds: int = 60,
              max_attempts: int = 3) -> dict | None:
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            while True:
                row = db.execute("""SELECT * FROM runs WHERE (status='queued' AND next_attempt<=?) OR
                                 (status='running' AND lease_until<?) ORDER BY id LIMIT 1""", (now, now)).fetchone()
                if row is None:
                    db.commit()
                    return None
                if int(row["attempts"]) >= max_attempts:
                    db.execute("""UPDATE runs SET status='failed',lease_owner=NULL,lease_until=NULL
                               WHERE id=?""", (row["id"],))
                    continue
                break
            db.execute("""UPDATE runs SET status='running',lease_owner=?,lease_until=?,
                       lease_generation=lease_generation+1,attempts=attempts+1 WHERE id=?""",
                       (owner, now + lease_seconds, row["id"]))
            db.commit()
            return self.get_run(int(row["id"]))

    def heartbeat(self, run_id: int, owner: str, generation: int, *, now: float | None = None,
                  lease_seconds: int = 60) -> bool:
        now = time.time() if now is None else now
        with self.connect() as db:
            cursor = db.execute("""UPDATE runs SET lease_until=? WHERE id=? AND status='running'
                                AND lease_owner=? AND lease_generation=? AND lease_until>=?""",
                                (now + lease_seconds, run_id, owner, generation, now))
            return cursor.rowcount == 1

    def confirm_metadata(self, run_id: int, owner: str, generation: int, installation_id: int,
                         repository_full_name: str, *, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self.connect() as db:
            cursor = db.execute("""UPDATE runs SET installation_id=?,repository_full_name=?,
                pending_installation_id=NULL,pending_repository_full_name=NULL
                WHERE id=? AND status='running' AND lease_owner=? AND lease_generation=?
                AND lease_until>=? AND pending_installation_id=? AND pending_repository_full_name=?""",
                (installation_id, repository_full_name, run_id, owner, generation, now,
                 installation_id, repository_full_name))
            if cursor.rowcount != 1:
                raise LeaseLost(run_id)

    def update_owned(self, run_id: int, owner: str, generation: int, *,
                     now: float | None = None, **fields: object) -> None:
        now = time.time() if now is None else now
        allowed = {"status", "result_json", "review_id", "check_id", "lease_until", "residual_race",
                   "ambiguity_kind", "ambiguous_since", "ambiguous_updated", "ambiguity_attempts"}
        if not fields or not set(fields) <= allowed:
            raise ValueError("invalid update")
        sql = ",".join(f"{key}=?" for key in fields)
        with self.connect() as db:
            cursor = db.execute(f"""UPDATE runs SET {sql} WHERE id=? AND status='running'
                                 AND lease_owner=? AND lease_generation=? AND lease_until>=?""",
                                (*fields.values(), run_id, owner, generation, now))  # noqa: S608
            if cursor.rowcount != 1:
                raise LeaseLost(run_id)

    def fail_and_retry(self, run_id: int, owner: str, generation: int, *, now: float | None = None,
                       max_attempts: int = 3) -> bool:
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT attempts FROM runs WHERE id=? AND status='running'
                             AND lease_owner=? AND lease_generation=? AND lease_until>=?""",
                             (run_id, owner, generation, now)).fetchone()
            if row is None:
                db.rollback()
                raise LeaseLost(run_id)
            retry = int(row["attempts"]) < max_attempts
            if retry:
                delay = min(300, 2 ** int(row["attempts"]))
                db.execute("""UPDATE runs SET status='queued',next_attempt=?,lease_owner=NULL,
                           lease_until=NULL WHERE id=?""", (now + delay, run_id))
            else:
                db.execute("UPDATE runs SET status='failed',lease_owner=NULL,lease_until=NULL WHERE id=?", (run_id,))
            db.commit()
            return retry

    def record_ambiguity(self, run_id: int, owner: str, generation: int, *, kind: str,
                         attempts: int, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self.connect() as db:
            cursor = db.execute("""UPDATE runs SET ambiguity_kind=?,
                ambiguous_since=COALESCE(ambiguous_since,?),ambiguous_updated=?,ambiguity_attempts=?
                WHERE id=? AND status='running' AND lease_owner=? AND lease_generation=?
                AND lease_until>=?""", (kind, now, now, attempts, run_id, owner, generation, now))
            if cursor.rowcount != 1:
                raise LeaseLost(run_id)

    def mark_ambiguous(self, run_id: int, owner: str, generation: int, *, kind: str,
                       attempts: int, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self.connect() as db:
            cursor = db.execute("""UPDATE runs SET status='ambiguous',ambiguity_kind=?,
                ambiguous_since=COALESCE(ambiguous_since,?),ambiguous_updated=?,ambiguity_attempts=?,
                lease_owner=NULL,lease_until=NULL WHERE id=? AND status='running' AND lease_owner=?
                AND lease_generation=? AND lease_until>=?""",
                (kind, now, now, attempts, run_id, owner, generation, now))
            if cursor.rowcount != 1:
                raise LeaseLost(run_id)

    def acquire_publication(self, run_id: int, owner: str, generation: int, *,
                            publication_owner: str | None = None,
                            snapshot_json: str | None = None,
                            now: float | None = None, lock_seconds: int = 120) -> dict | None:
        now = time.time() if now is None else now
        publication_owner = owner if publication_owner is None else publication_owner
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT publication_owner,publication_generation,publication_until,
                              snapshot_json FROM runs WHERE id=? AND status='running' AND lease_owner=?
                              AND lease_generation=? AND lease_until>=?""",
                             (run_id, owner, generation, now)).fetchone()
            if row is None:
                db.rollback()
                return None
            existing_snapshot = row["snapshot_json"]
            active = row["publication_owner"] is not None and row["publication_until"] is not None \
                and float(row["publication_until"]) >= now
            if active and row["publication_owner"] != publication_owner:
                db.rollback()
                return None
            if existing_snapshot is not None and snapshot_json is not None and existing_snapshot != snapshot_json:
                db.rollback()
                raise ValueError("publication snapshot is immutable")
            if existing_snapshot is None and snapshot_json is None:
                # Compatibility callers may lock first, but side effects must not begin until a snapshot is stored.
                snapshot_json = None
            chosen_snapshot = existing_snapshot if existing_snapshot is not None else snapshot_json
            next_generation = int(row["publication_generation"]) + (0 if active else 1)
            db.execute("""UPDATE runs SET publication_owner=?,publication_generation=?,publication_until=?,
                       snapshot_json=COALESCE(snapshot_json,?) WHERE id=?""",
                       (publication_owner, next_generation, now + lock_seconds, chosen_snapshot, run_id))
            db.commit()
            return {"owner": publication_owner, "generation": next_generation,
                    "until": now + lock_seconds, "snapshot_json": chosen_snapshot}

    def heartbeat_publication(self, run_id: int, owner: str, generation: int,
                              publication_owner: str, publication_generation: int, *,
                              now: float | None = None, lock_seconds: int = 120) -> bool:
        now = time.time() if now is None else now
        with self.connect() as db:
            cursor = db.execute("""UPDATE runs SET publication_until=? WHERE id=? AND status='running'
                                AND lease_owner=? AND lease_generation=? AND lease_until>=?
                                AND publication_owner=? AND publication_generation=?
                                AND publication_until>=?""",
                                (now + lock_seconds, run_id, owner, generation, now,
                                 publication_owner, publication_generation, now))
            return cursor.rowcount == 1

    def record_publication(self, run_id: int, owner: str, generation: int,
                           *, review_id: int | None = None, check_id: int | None = None,
                           now: float | None = None, publication_owner: str | None = None,
                           publication_generation: int | None = None) -> None:
        fields = {key: value for key, value in {"review_id": review_id, "check_id": check_id}.items()
                  if value is not None}
        if publication_owner is not None and publication_generation is not None:
            now = time.time() if now is None else now
            sql = ",".join(f"{key}=?" for key in fields)
            with self.connect() as db:
                cursor = db.execute(f"""UPDATE runs SET {sql} WHERE id=? AND status='running'
                    AND lease_owner=? AND lease_generation=? AND lease_until>=?
                    AND publication_owner=? AND publication_generation=? AND publication_until>=?""",
                    (*fields.values(), run_id, owner, generation, now, publication_owner,
                     publication_generation, now))  # noqa: S608
                if cursor.rowcount != 1:
                    raise LeaseLost(run_id)
            return
        self.update_owned(run_id, owner, generation, now=now, **fields)

    def finalize_publication(self, run_id: int, owner: str, generation: int,
                             publication_owner: str, publication_generation: int, *,
                             result_json: str, review_id: int, check_id: int,
                             now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self.connect() as db:
            cursor = db.execute("""UPDATE runs SET status='completed',result_json=?,review_id=?,check_id=?
                WHERE id=? AND status='running' AND lease_owner=? AND lease_generation=? AND lease_until>=?
                AND publication_owner=? AND publication_generation=? AND publication_until>=?""",
                (result_json, review_id, check_id, run_id, owner, generation, now,
                 publication_owner, publication_generation, now))
            if cursor.rowcount != 1:
                raise LeaseLost(run_id)

    def cancel_owned(self, run_id: int, owner: str, generation: int, *, now: float | None = None) -> None:
        run = self.get_run(run_id)
        residual = int(run["review_id"] is not None or run["check_id"] is not None)
        self.update_owned(run_id, owner, generation, now=now, status="cancelled", residual_race=residual)
