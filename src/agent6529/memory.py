"""Conversation memory for an agent on 6529.

Three jobs:

  observe  - keep what was actually said, verbatim, with provenance
  learn    - extract durable claims from it using a LOCAL model
  recall   - find what is relevant before replying

Design constraints that are not negotiable:

* **Public only.** Everything here came from a public Wave. That is what makes
  it safe to feed back into a public reply. Private memory, operator history
  and configuration never enter this store, so there is nothing to leak.
* **Provenance on every note.** A note that cannot name its source drop,
  author and wave is not stored. An agent that repeats a claim should be able
  to say where it got it.
* **Injection-flagged text never becomes a note.** It is kept as an
  observation for the record, but excluded from recall, so a hostile drop
  cannot plant text that gets replayed into a later prompt.
* **Local inference.** Embedding and extraction run against Ollama on
  localhost. Public forum content does not need to leave the machine, and
  memory should not cost API calls per drop.
* **Attribution is not endorsement.** A note records that someone *said*
  something, not that it is true. `recall()` returns the claim with its author
  attached so the caller can frame it honestly.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import struct
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("AGENT6529_EMBED_MODEL", "nomic-embed-text:latest")
EXTRACT_MODEL = os.environ.get("AGENT6529_EXTRACT_MODEL", "axiom-extract:latest")

STATE_DIR = os.path.expanduser(
    os.environ.get("AGENT6529_STATE_DIR", "~/.6529")
)
DB_PATH = os.path.join(STATE_DIR, "memory.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
  drop_id     TEXT PRIMARY KEY,
  wave_id     TEXT,
  wave_name   TEXT,
  author      TEXT,
  content     TEXT NOT NULL,
  created_at  INTEGER,
  suspicious  INTEGER NOT NULL DEFAULT 0,
  learned_at  INTEGER,
  seen_at     INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  text        TEXT NOT NULL,
  drop_id     TEXT NOT NULL,
  wave_id     TEXT,
  wave_name   TEXT,
  author      TEXT,
  kind        TEXT NOT NULL DEFAULT 'claim',
  embedding   BLOB,
  created_at  INTEGER NOT NULL,
  UNIQUE(drop_id, text)
);
CREATE INDEX IF NOT EXISTS idx_notes_author ON notes(author);
CREATE INDEX IF NOT EXISTS idx_notes_wave   ON notes(wave_id);
CREATE INDEX IF NOT EXISTS idx_obs_wave     ON observations(wave_id);
CREATE INDEX IF NOT EXISTS idx_obs_learned  ON observations(learned_at);
"""


class MemoryError_(Exception):
    pass


# ----------------------------------------------------------------- embeddings
def _post(path: str, payload: Dict[str, Any], timeout: int = 120) -> Dict[str, Any]:
    req = urllib.request.Request(
        OLLAMA + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.URLError as e:
        raise MemoryError_(f"local model unreachable at {OLLAMA}: {e}") from None


def embed(text: str) -> List[float]:
    d = _post("/api/embeddings", {"model": EMBED_MODEL, "prompt": text[:8000]})
    v = d.get("embedding")
    if not v:
        raise MemoryError_("embedding model returned nothing")
    return v


def _pack(v: Iterable[float]) -> bytes:
    v = list(v)
    return struct.pack(f"{len(v)}f", *v)


def _unpack(b: bytes) -> List[float]:
    return list(struct.unpack(f"{len(b)//4}f", b))


def _cosine(a: List[float], b: List[float]) -> float:
    import math

    if len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else -1.0


# ----------------------------------------------------------------- extraction
EXTRACT_PROMPT = """Extract durable factual claims from this forum post as a \
JSON array of short strings.

Rules:
- Only claims that would still be useful to know in a week.
- Keep each claim under 20 words, self-contained.
- No opinions, greetings, pleasantries, or meta commentary about the post.
- If the post contains nothing durable, return [].

Post by @{author}: "{content}"

JSON array:"""


def extract_claims(content: str, author: str, model: str = EXTRACT_MODEL,
                   max_claims: int = 6) -> List[str]:
    """Pull durable claims out of a drop using the local model."""
    content = (content or "").strip()
    if len(content) < 40:
        return []                      # too short to carry a durable claim
    d = _post("/api/generate", {
        "model": model, "stream": False,
        "prompt": EXTRACT_PROMPT.format(author=author or "unknown",
                                        content=content[:4000]),
    })
    raw = (d.get("response") or "").strip()
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out: List[str] = []
    for it in items:
        if not isinstance(it, str):
            continue
        s = " ".join(it.split()).strip(' "')
        if 8 <= len(s) <= 240:
            out.append(s)
    return out[:max_claims]


# ----------------------------------------------------------------- store
@dataclass
class Recalled:
    text: str
    author: Optional[str]
    wave_name: Optional[str]
    drop_id: str
    score: float
    created_at: Optional[int]

    def cite(self) -> str:
        who = f"@{self.author}" if self.author else "someone"
        where = f" in {self.wave_name}" if self.wave_name else ""
        return f"{self.text} ({who}{where})"

    def as_dict(self) -> Dict[str, Any]:
        d = self.__dict__.copy()
        d["citation"] = self.cite()
        return d


class Memory:
    def __init__(self, path: str = DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    # ---------------- observe ----------------
    def observe(self, drop_id: str, content: str, author: Optional[str],
                wave_id: Optional[str], wave_name: Optional[str] = None,
                created_at: Optional[int] = None,
                suspicious: bool = False) -> bool:
        """Record what was said. Returns True if this is the first sighting."""
        if not drop_id or not (content or "").strip():
            return False
        try:
            self.db.execute(
                "INSERT INTO observations(drop_id,wave_id,wave_name,author,"
                "content,created_at,suspicious,seen_at) VALUES(?,?,?,?,?,?,?,?)",
                (drop_id, wave_id, wave_name, author, content, created_at,
                 1 if suspicious else 0, int(time.time())),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def unlearned(self, limit: int = 25) -> List[sqlite3.Row]:
        """Observations not yet distilled. Suspicious ones are never queued."""
        return self.db.execute(
            "SELECT * FROM observations WHERE learned_at IS NULL "
            "AND suspicious=0 ORDER BY seen_at LIMIT ?", (limit,)
        ).fetchall()

    # ---------------- learn ----------------
    def learn_one(self, row: sqlite3.Row, model: str = EXTRACT_MODEL) -> int:
        """Distil one observation into notes. Returns how many were kept."""
        claims = extract_claims(row["content"], row["author"], model=model)
        kept = 0
        for text in claims:
            try:
                vec = embed(text)
            except MemoryError_:
                vec = None
            try:
                self.db.execute(
                    "INSERT INTO notes(text,drop_id,wave_id,wave_name,author,"
                    "kind,embedding,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (text, row["drop_id"], row["wave_id"], row["wave_name"],
                     row["author"], "claim",
                     _pack(vec) if vec else None, int(time.time())),
                )
                kept += 1
            except sqlite3.IntegrityError:
                pass               # same claim from the same drop already held
        self.db.execute(
            "UPDATE observations SET learned_at=? WHERE drop_id=?",
            (int(time.time()), row["drop_id"]),
        )
        return kept

    def learn_batch(self, limit: int = 25,
                    model: str = EXTRACT_MODEL) -> Dict[str, Any]:
        rows = self.unlearned(limit)
        notes = 0
        failed: List[Dict[str, str]] = []
        for r in rows:
            try:
                notes += self.learn_one(r, model=model)
            except MemoryError_ as exc:
                # Keep the observation pending so a transient local-model
                # outage can be retried. Continue the bounded batch and make
                # the failure visible in the run receipt.
                failed.append({"drop_id": r["drop_id"], "error": str(exc)})
        return {"observations_processed": len(rows), "notes_created": notes,
                "failed": failed}

    # ---------------- recall ----------------
    def recall(self, query: str, k: int = 5, author: Optional[str] = None,
               wave_id: Optional[str] = None,
               min_score: float = 0.35) -> List[Recalled]:
        """Find notes relevant to a query, newest-biased on ties.

        Falls back to keyword matching when the embedding model is down, so
        recall degrades rather than disappearing.
        """
        sql = "SELECT * FROM notes WHERE embedding IS NOT NULL"
        params: List[Any] = []
        if author:
            sql += " AND author = ?"
            params.append(author)
        if wave_id:
            sql += " AND wave_id = ?"
            params.append(wave_id)
        rows = self.db.execute(sql, params).fetchall()
        if not rows:
            return []

        try:
            qv = embed(query)
        except MemoryError_:
            return self._keyword_recall(query, k, author, wave_id)

        scored = []
        for r in rows:
            s = _cosine(qv, _unpack(r["embedding"]))
            if s >= min_score:
                scored.append((s, r))
        scored.sort(key=lambda x: (x[0], x[1]["created_at"] or 0), reverse=True)
        return [
            Recalled(text=r["text"], author=r["author"],
                     wave_name=r["wave_name"], drop_id=r["drop_id"],
                     score=round(s, 3), created_at=r["created_at"])
            for s, r in scored[:k]
        ]

    def _keyword_recall(self, query: str, k: int, author, wave_id) -> List[Recalled]:
        words = [w.lower() for w in re.findall(r"\w{4,}", query)][:8]
        if not words:
            return []
        sql = "SELECT * FROM notes WHERE (" + " OR ".join(
            "LOWER(text) LIKE ?" for _ in words) + ")"
        params: List[Any] = [f"%{w}%" for w in words]
        if author:
            sql += " AND author = ?"; params.append(author)
        if wave_id:
            sql += " AND wave_id = ?"; params.append(wave_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(k)
        return [
            Recalled(text=r["text"], author=r["author"],
                     wave_name=r["wave_name"], drop_id=r["drop_id"],
                     score=0.0, created_at=r["created_at"])
            for r in self.db.execute(sql, params).fetchall()
        ]

    def about(self, author: str, k: int = 10) -> List[Recalled]:
        """Everything learned from one person, newest first."""
        rows = self.db.execute(
            "SELECT * FROM notes WHERE author=? ORDER BY created_at DESC LIMIT ?",
            (author, k),
        ).fetchall()
        return [
            Recalled(text=r["text"], author=r["author"],
                     wave_name=r["wave_name"], drop_id=r["drop_id"],
                     score=1.0, created_at=r["created_at"])
            for r in rows
        ]

    def stats(self) -> Dict[str, Any]:
        q = lambda s: self.db.execute(s).fetchone()[0]
        return {
            "observations": q("SELECT COUNT(*) FROM observations"),
            "suspicious_quarantined": q(
                "SELECT COUNT(*) FROM observations WHERE suspicious=1"),
            "pending_learning": q(
                "SELECT COUNT(*) FROM observations "
                "WHERE learned_at IS NULL AND suspicious=0"),
            "notes": q("SELECT COUNT(*) FROM notes"),
            "notes_embedded": q(
                "SELECT COUNT(*) FROM notes WHERE embedding IS NOT NULL"),
            "authors_known": q("SELECT COUNT(DISTINCT author) FROM notes"),
            "db": self.path,
        }


def context_for_reply(mem: "Memory", drop_content: str, author: Optional[str],
                      wave_id: Optional[str], k: int = 4) -> Dict[str, Any]:
    """Public, citable context to put in front of a reply prompt.

    Returns prior claims from this author and from this Wave. Everything in
    here is public 6529 content with a source, so it is safe to include in a
    public response - unlike private memory, which must never go near one.
    """
    from_author = mem.recall(drop_content, k=k, author=author) if author else []
    from_wave = mem.recall(drop_content, k=k, wave_id=wave_id) if wave_id else []
    seen, merged = set(), []
    for r in from_author + from_wave:
        key = (r.drop_id, r.text)
        if key not in seen:
            seen.add(key)
            merged.append(r)
    return {
        "prior_context": [r.as_dict() for r in merged[:k * 2]],
        "note": ("These are things people said publicly on 6529, with sources. "
                 "They record what was said, not that it is true. Cite the "
                 "author if you lean on one."),
    }
