"""Durable state for the 6529 connector.

SQLite under the state dir so cron runs, interactive runs, and
restarts share one source of truth.

Separation that matters:
  * `cursors`      — ingestion progress only. Advanced *after* events are
                     persisted, never because a reply was produced.
  * `seen_events`  — dedupe across routes (wave feed vs notifications).
  * `outbox`       — one row per logical outgoing action, carrying the
                     client_drop_id and the exact frozen payload.

An outbox row is written *before* the HTTP call, so a lost response can be
recovered by reusing the same client_drop_id and payload verbatim.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

STATE_DIR = os.path.expanduser(
    os.environ.get("SIXTY529_STATE_DIR", "~/.sixty529")
)
DB_PATH = os.path.join(STATE_DIR, "connector.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cursors (
  scope          TEXT PRIMARY KEY,
  serial_no      INTEGER,
  last_id        TEXT,
  updated_at     INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS seen_events (
  event_key      TEXT PRIMARY KEY,   -- canonical drop id (route-independent)
  wave_id        TEXT,
  source_route   TEXT,
  first_seen_at  INTEGER NOT NULL,
  processed_at   INTEGER
);
CREATE TABLE IF NOT EXISTS outbox (
  client_drop_id TEXT PRIMARY KEY,
  wave_id        TEXT NOT NULL,
  reply_to_id    TEXT,
  payload_json   TEXT NOT NULL,      -- exact frozen request body
  content_hash   TEXT NOT NULL,      -- changed draft => new action
  status         TEXT NOT NULL,      -- draft|pending|sent|failed|abandoned
  attempts       INTEGER NOT NULL DEFAULT 0,
  server_drop_id TEXT,
  last_error     TEXT,
  created_at     INTEGER NOT NULL,
  updated_at     INTEGER NOT NULL,
  verified_at    INTEGER
);
CREATE TABLE IF NOT EXISTS post_log (
  server_drop_id TEXT PRIMARY KEY,
  wave_id        TEXT,
  client_drop_id TEXT,
  posted_at      INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status);
CREATE INDEX IF NOT EXISTS idx_seen_wave ON seen_events(wave_id);
"""


def _hash(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: str = DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    # ---------- meta ----------
    def get_meta(self, key: str, default=None):
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_meta(self, key: str, value: str):
        self.db.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )

    # ---------- cursors ----------
    def get_cursor(self, scope: str) -> Optional[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM cursors WHERE scope=?", (scope,)
        ).fetchone()

    def advance_cursor(self, scope: str, serial_no=None, last_id=None):
        """Only call after the corresponding events are durably persisted."""
        self.db.execute(
            "INSERT INTO cursors(scope,serial_no,last_id,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(scope) DO UPDATE SET "
            "  serial_no=COALESCE(excluded.serial_no,cursors.serial_no),"
            "  last_id=COALESCE(excluded.last_id,cursors.last_id),"
            "  updated_at=excluded.updated_at",
            (scope, serial_no, last_id, int(time.time())),
        )

    # ---------- events ----------
    def record_event(self, event_key: str, wave_id: str, route: str) -> bool:
        """Returns True if newly recorded, False if already seen (any route)."""
        try:
            self.db.execute(
                "INSERT INTO seen_events(event_key,wave_id,source_route,first_seen_at) "
                "VALUES(?,?,?,?)",
                (event_key, wave_id, route, int(time.time())),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def is_seen(self, event_key: str) -> bool:
        return (
            self.db.execute(
                "SELECT 1 FROM seen_events WHERE event_key=?", (event_key,)
            ).fetchone()
            is not None
        )

    def mark_processed(self, event_key: str):
        self.db.execute(
            "UPDATE seen_events SET processed_at=? WHERE event_key=?",
            (int(time.time()), event_key),
        )

    # ---------- outbox ----------
    def create_action(
        self,
        wave_id: str,
        payload: Dict[str, Any],
        reply_to_id: Optional[str] = None,
        status: str = "draft",
    ) -> str:
        """One logical action. client_drop_id is minted here and frozen."""
        cdid = payload.get("client_drop_id") or str(uuid.uuid4())
        payload = dict(payload)
        payload["client_drop_id"] = cdid
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        now = int(time.time())
        self.db.execute(
            "INSERT INTO outbox(client_drop_id,wave_id,reply_to_id,payload_json,"
            "content_hash,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (cdid, wave_id, reply_to_id, body, _hash(body), status, now, now),
        )
        return cdid

    def get_action(self, cdid: str) -> Optional[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM outbox WHERE client_drop_id=?", (cdid,)
        ).fetchone()

    def list_actions(self, status: Optional[str] = None) -> List[sqlite3.Row]:
        if status:
            return self.db.execute(
                "SELECT * FROM outbox WHERE status=? ORDER BY created_at", (status,)
            ).fetchall()
        return self.db.execute(
            "SELECT * FROM outbox ORDER BY created_at DESC LIMIT 100"
        ).fetchall()

    def set_status(self, cdid: str, status: str, error: Optional[str] = None,
                   server_drop_id: Optional[str] = None, bump_attempts=False):
        self.db.execute(
            "UPDATE outbox SET status=?, last_error=?, "
            "server_drop_id=COALESCE(?,server_drop_id), "
            "attempts=attempts+? , updated_at=? WHERE client_drop_id=?",
            (status, error, server_drop_id, 1 if bump_attempts else 0,
             int(time.time()), cdid),
        )

    def mark_verified(self, cdid: str, server_drop_id: str, wave_id: str):
        now = int(time.time())
        self.db.execute(
            "UPDATE outbox SET status='sent', server_drop_id=?, verified_at=?, "
            "updated_at=? WHERE client_drop_id=?",
            (server_drop_id, now, now, cdid),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO post_log(server_drop_id,wave_id,client_drop_id,"
            "posted_at) VALUES(?,?,?,?)",
            (server_drop_id, wave_id, cdid, now),
        )

    def already_replied_to(self, parent_drop_id: str) -> bool:
        return (
            self.db.execute(
                "SELECT 1 FROM outbox WHERE reply_to_id=? AND status IN "
                "('pending','sent') LIMIT 1",
                (parent_drop_id,),
            ).fetchone()
            is not None
        )

    def posts_since(self, since_epoch: int) -> int:
        r = self.db.execute(
            "SELECT COUNT(*) c FROM post_log WHERE posted_at>=?", (since_epoch,)
        ).fetchone()
        return int(r["c"]) if r else 0

    def last_post_at(self, wave_id: Optional[str] = None) -> Optional[int]:
        if wave_id:
            r = self.db.execute(
                "SELECT MAX(posted_at) m FROM post_log WHERE wave_id=?", (wave_id,)
            ).fetchone()
        else:
            r = self.db.execute("SELECT MAX(posted_at) m FROM post_log").fetchone()
        return r["m"] if r and r["m"] else None

    # ---------- job lock ----------
    def acquire_job_lock(self, name: str, ttl: int = 600) -> bool:
        """Prevent overlapping ingestion jobs from double-publishing."""
        now = int(time.time())
        cur = self.get_meta(f"lock:{name}")
        if cur:
            try:
                if int(cur) + ttl > now:
                    return False
            except ValueError:
                pass
        self.set_meta(f"lock:{name}", now)
        return True

    def release_job_lock(self, name: str):
        self.db.execute("DELETE FROM meta WHERE key=?", (f"lock:{name}",))
