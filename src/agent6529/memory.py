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
  -- Which surface this was said on. One store, so a person met in two
  -- places is one history, while recall can still be scoped to one.
  source      TEXT NOT NULL DEFAULT '6529',
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
  -- Who is entitled to assert this. A claim ABOUT someone may only be made
  -- by them, by the operator, or by their own public post. Anything else is
  -- third_party: kept for the record, never recalled as fact. Without this,
  -- anyone who can post can write the agent's memory about anyone.
  asserted_by TEXT NOT NULL DEFAULT 'public_post_by_self',
  subject     TEXT,
  -- Supersession. No shipping memory system enforces retraction, so it is
  -- built here: invalidate, never delete, and filter at the read boundary.
  status      TEXT NOT NULL DEFAULT 'active',
  supersedes  INTEGER,
  valid_to    INTEGER,
  source      TEXT NOT NULL DEFAULT '6529',
  UNIQUE(drop_id, text)
);
CREATE INDEX IF NOT EXISTS idx_notes_author ON notes(author);
CREATE INDEX IF NOT EXISTS idx_notes_wave   ON notes(wave_id);
CREATE INDEX IF NOT EXISTS idx_obs_wave     ON observations(wave_id);
CREATE INDEX IF NOT EXISTS idx_obs_learned  ON observations(learned_at);
"""

# Added after the table may already exist. Applied one at a time so an older
# database upgrades in place without losing rows.
MIGRATIONS = [
    "ALTER TABLE observations ADD COLUMN source TEXT NOT NULL DEFAULT '6529'",
    "ALTER TABLE notes ADD COLUMN source TEXT NOT NULL DEFAULT '6529'",
    "CREATE INDEX IF NOT EXISTS idx_notes_source ON notes(source)",
    "CREATE INDEX IF NOT EXISTS idx_obs_source ON observations(source)",
    "ALTER TABLE notes ADD COLUMN asserted_by TEXT NOT NULL DEFAULT 'public_post_by_self'",
    "ALTER TABLE notes ADD COLUMN subject TEXT",
    "ALTER TABLE notes ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
    "ALTER TABLE notes ADD COLUMN supersedes INTEGER",
    "ALTER TABLE notes ADD COLUMN valid_to INTEGER",
    "CREATE INDEX IF NOT EXISTS idx_notes_status ON notes(status)",
    "CREATE INDEX IF NOT EXISTS idx_notes_subject ON notes(subject)",
]

# Lexical half of retrieval. Content is identifier-dense (rc.12, 0xef2cc7d1,
# handles) and embeddings blur exact tokens; BM25 is the only thing that
# separates rc.11 from rc.12. Contentless FTS5 indexed by rowid = notes.id.
FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
  USING fts5(text, content='notes', content_rowid='id', tokenize='porter unicode61');
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
  INSERT INTO notes_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, text) VALUES('delete', old.id, old.text);
  INSERT INTO notes_fts(rowid, text) VALUES (new.id, new.text);
END;
"""

# Who may assert a claim about whom.
TRUSTED_ASSERTERS = ("self", "operator", "public_post_by_self")

# Bumped when the lexical index needs rebuilding from the notes table. Tracked
# in PRAGMA user_version so the rebuild happens once, not on every open.
SCHEMA_VERSION = 2


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
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError,
            json.JSONDecodeError) as e:
        # URLError alone is not enough: a socket timeout raises TimeoutError and
        # a half-read response raises JSONDecodeError, neither of which subclass
        # it. Letting those escape crashes recall instead of degrading it, and a
        # slow-but-alive Ollama is the expected failure on a loaded machine.
        raise MemoryError_(f"local model unavailable at {OLLAMA}: "
                           f"{type(e).__name__}") from None


def contextualize(text: str, author: Optional[str] = None,
                  wave_name: Optional[str] = None,
                  created_at: Optional[int] = None) -> str:
    """Prepend who/where/when before embedding.

    An extracted claim loses its anchors - "rebuilds the Merkle tree from
    scratch" has no subject, and "turn it back on today" has no referent or
    date. Measured on this corpus, a one-line header lifted P@1 from 0.500 to
    0.750 and MRR from 0.708 to 0.854, with no model call. Appending the whole
    source post on top of the header added nothing further.
    """
    bits = []
    if wave_name:
        bits.append(wave_name)
    if author:
        bits.append(f"@{author}")
    if created_at:
        try:
            import datetime
            ts = created_at / 1000 if created_at > 1e11 else created_at
            bits.append(datetime.datetime.fromtimestamp(
                ts, datetime.timezone.utc).strftime("%Y-%m-%d"))
        except (ValueError, OSError, OverflowError):
            pass
    return f"[{' / '.join(bits)}] {text}" if bits else text


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
- Resolve pronouns and references: write "the validator", not "it".
- Replace relative time ("today", "tomorrow", "last week") with the actual
  date. This post was written on {date}.
- If a claim only makes sense inside this one conversation, leave it out.
- If the post contains nothing durable, return [].

Post by @{author}: "{content}"

JSON array:"""


_HANDLE = re.compile(r"@\[?([A-Za-z0-9_]{2,30})\]?")


def _row_source(row) -> str:
    """An older observation row has no source column; it predates Twitter."""
    try:
        return row["source"] or "6529"
    except (IndexError, KeyError):
        return "6529"


_ADDRESSING = re.compile(r"^\s*(?:@\[?[A-Za-z0-9_]{2,30}\]?[\s,:]*)+")

# Surfaces where a reply opens by naming who it answers, so a leading handle
# is addressing rather than subject. This is a platform convention, not a
# fact about language: on 6529 "@bob runs the validator" is a claim about bob,
# while on Twitter "@bob agreed" is just how a reply is addressed. Reading
# the prefix as a subject there would tier nearly everything said TO this
# agent as third_party and drop it from recall.
ADDRESSING_SURFACES = ("twitter",)


def _subject_of(text: str, source: str = "6529") -> Optional[str]:
    """The person a claim is about, if it names one.

    Only an explicit @handle counts, and never one that is merely addressing.
    Guessing a subject from prose would create exactly the false
    attributions this gate exists to prevent.
    """
    body = text or ""
    if source in ADDRESSING_SURFACES:
        body = _ADDRESSING.sub("", body, count=1)
    m = _HANDLE.search(body)
    return m.group(1) if m else None


def _date_of(created_at: Optional[int]) -> str:
    if not created_at:
        return "an unknown date"
    try:
        import datetime
        ts = created_at / 1000 if created_at > 1e11 else created_at
        return datetime.datetime.fromtimestamp(
            ts, datetime.timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return "an unknown date"


def extract_claims(content: str, author: str, model: str = EXTRACT_MODEL,
                   max_claims: int = 6,
                   created_at: Optional[int] = None) -> List[str]:
    """Pull durable claims out of a drop using the local model."""
    content = (content or "").strip()
    if len(content) < 40:
        return []                      # too short to carry a durable claim
    # think=False is load-bearing, not an optimisation. axiom-extract is built
    # on a hybrid reasoning model; Ollama routes its reasoning to a separate
    # `thinking` field, and on a real-length post it spends the entire
    # num_predict budget there and returns an EMPTY `response`. Measured on
    # backlogged observations: default -> resp=0, eval=1024, done=length, 39s.
    # With think=False -> resp=370, eval=95, done=stop, 4.4s.
    d = _post("/api/generate", {
        "model": model, "stream": False, "think": False,
        "prompt": EXTRACT_PROMPT.format(author=author or "unknown",
                                        content=content[:4000],
                                        date=_date_of(created_at)),
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
    # The post the claim came from. An extracted claim can lose its referent
    # ("leave it on tomorrow"); the source was always in the database and
    # simply was not returned. Carrying it lets the caller resolve the
    # reference instead of repeating a fragment.
    source: Optional[str] = None
    # Which surface it was said on. Named apart from `source` above, which is
    # the originating post's text.
    surface: str = "6529"

    def cite(self) -> str:
        who = f"@{self.author}" if self.author else "someone"
        where = f" in {self.wave_name}" if self.wave_name else ""
        on = "" if self.surface == "6529" else f" on {self.surface}"
        return f"{self.text} ({who}{where}{on})"

    def as_dict(self) -> Dict[str, Any]:
        d = self.__dict__.copy()
        d["citation"] = self.cite()
        return d


class Memory:
    operator_handles: tuple = tuple(
        h for h in os.environ.get("AGENT6529_OPERATOR_HANDLES", "").split(",") if h
    )

    def __init__(self, path: Optional[str] = None):
        # Resolved at call time, not bound as a default: the state directory
        # can be set after this module is imported.
        path = path or DB_PATH
        self._fts = False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Bring an older database forward in place.

        Each step is attempted independently and a duplicate-column error is
        expected on an already-migrated database, so this is idempotent. A
        migration failure must never take down a cron run that only wanted to
        read, so everything here is best-effort and the store stays usable.
        """
        for stmt in MIGRATIONS:
            try:
                self.db.execute(stmt)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    pass            # index already present, or similar
        try:
            self.db.executescript(FTS_SCHEMA)
            # Notes written before the index existed are invisible to it. An
            # external-content FTS5 table cannot be diffed against its content
            # table - a plain scan reads straight through to notes and every
            # row looks present - so backfill is a one-shot 'rebuild', guarded
            # by the schema version rather than repeated on every open.
            if self._user_version() < SCHEMA_VERSION:
                self.db.execute(
                    "INSERT INTO notes_fts(notes_fts) VALUES('rebuild')")
                self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._fts = True
        except sqlite3.Error:
            self._fts = False       # no FTS5 build: dense-only still works

    def _user_version(self) -> int:
        try:
            return int(self.db.execute("PRAGMA user_version").fetchone()[0])
        except (sqlite3.Error, TypeError, ValueError):
            return 0

    def close(self):
        self.db.close()

    # ---------------- observe ----------------
    def observe(self, drop_id: str, content: str, author: Optional[str],
                wave_id: Optional[str], wave_name: Optional[str] = None,
                created_at: Optional[int] = None,
                suspicious: bool = False,
                source: str = "6529") -> bool:
        """Record what was said. Returns True if this is the first sighting."""
        if not drop_id or not (content or "").strip():
            return False
        try:
            self.db.execute(
                "INSERT INTO observations(drop_id,wave_id,wave_name,author,"
                "content,created_at,suspicious,seen_at,source) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (drop_id, wave_id, wave_name, author, content, created_at,
                 1 if suspicious else 0, int(time.time()), source),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def unlearned(self, limit: int = 25) -> List[sqlite3.Row]:
        """Observations not yet distilled. Suspicious ones are never queued."""
        if limit < 0:
            raise ValueError("learning limit must be non-negative")
        return self.db.execute(
            "SELECT * FROM observations WHERE learned_at IS NULL "
            "AND suspicious=0 ORDER BY seen_at LIMIT ?", (limit,)
        ).fetchall()

    # ---------------- learn ----------------
    @staticmethod
    def assertion_tier(author: Optional[str], subject: Optional[str],
                       operator_handles: Iterable[str] = ()) -> str:
        """Who is making this claim, about whom.

        A post is self-assertion when its author is also its subject, operator
        when the author is the operator, and third_party otherwise. Third-party
        claims are stored but never recalled as fact.
        """
        a = (author or "").lower()
        if a and a in {h.lower() for h in operator_handles}:
            return "operator"
        if subject and a and a == subject.lower():
            return "self"
        if not subject:
            return "public_post_by_self"   # a statement about the world
        return "third_party"

    def learn_one(self, row: sqlite3.Row, model: str = EXTRACT_MODEL) -> int:
        """Distil one observation into notes. Returns how many were kept."""
        claims = extract_claims(row["content"], row["author"], model=model,
                                created_at=row["created_at"])
        kept = 0
        for text in claims:
            try:
                vec = embed(contextualize(text, row["author"], row["wave_name"],
                                          row["created_at"]))
            except MemoryError_:
                vec = None
            try:
                subject = _subject_of(text, _row_source(row))
                tier = self.assertion_tier(row["author"], subject,
                                           self.operator_handles)
                self.db.execute(
                    "INSERT INTO notes(text,drop_id,wave_id,wave_name,author,"
                    "kind,embedding,created_at,asserted_by,subject,status,"
                    "source) VALUES(?,?,?,?,?,?,?,?,?,?,'active',?)",
                    (text, row["drop_id"], row["wave_id"], row["wave_name"],
                     row["author"], "claim",
                     _pack(vec) if vec else None, int(time.time()),
                     tier, subject, _row_source(row)),
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
    # Calibrated against nomic-embed-text, where deliberately unrelated text
    # pairs score min 0.300 / median 0.441 / p95 0.519. A 0.35 floor is BELOW
    # the noise floor: 95.8% of unrelated pairs clear it, so it filtered
    # nothing and the agent could never answer "I don't know" - it always
    # returned k confident-looking irrelevant memories. These numbers are
    # model-specific; recalibrate if the embedding model changes.
    MIN_SCORE = 0.50          # absolute floor, for abstention
    RELATIVE_GAP = 0.06       # drop anything well below the best hit

    def recall(self, query: str, k: int = 5, author: Optional[str] = None,
               wave_id: Optional[str] = None,
               min_score: Optional[float] = None,
               source: Optional[str] = None) -> List[Recalled]:
        """Find notes relevant to a query, newest-biased on ties.

        Falls back to keyword matching when the embedding model is down, so
        recall degrades rather than disappearing.
        """
        sql = ("SELECT * FROM notes WHERE embedding IS NOT NULL"
               " AND status = 'active'"
               f" AND asserted_by IN ({','.join('?' * len(TRUSTED_ASSERTERS))})")
        params: List[Any] = list(TRUSTED_ASSERTERS)
        if author:
            sql += " AND author = ?"
            params.append(author)
        if wave_id:
            sql += " AND wave_id = ?"
            params.append(wave_id)
        if source:
            sql += " AND source = ?"
            params.append(source)
        rows = self.db.execute(sql, params).fetchall()

        floor = self.MIN_SCORE if min_score is None else min_score
        scored: List[Any] = []
        if rows:
            try:
                qv = embed(query)
            except MemoryError_:
                # Model down. Lexical is a real index, not a guess, so prefer
                # it over LIKE scanning; keep LIKE for a no-FTS build.
                lex = self._lexical(query, k, author, wave_id, source)
                if lex:
                    return [self._mk(r, 0.0) for r in lex]
                return self._keyword_recall(query, k, author, wave_id, source)
            for r in rows:
                s = _cosine(qv, _unpack(r["embedding"]))
                if s >= floor:
                    scored.append((s, r))
        scored.sort(key=lambda x: (x[0], x[1]["created_at"] or 0), reverse=True)
        scored = scored[:k]
        # Relative gap: once the best hit is known, anything far below it is
        # noise even if it cleared the floor. Measured: precision 0.20 -> 0.50
        # at no cost to P@1.
        if scored:
            cutoff = scored[0][0] - self.RELATIVE_GAP
            scored = [(s, r) for s, r in scored if s >= cutoff]

        # Fuse with BM25. Embeddings encode what text is ABOUT, not which
        # characters it contains, so "rc.11" and "rc.12" land almost on top of
        # each other. Lexical search is the only half that separates them, and
        # this content is full of versions, handles and addresses.
        # A lexical hit deliberately bypasses the cosine floor: an exact
        # identifier match is strong evidence even when the embedding is cold.
        lex = self._lexical(query, k * 2, author, wave_id, source)
        if lex:
            return self._fuse(scored, lex, k, qv)
        if not scored and not rows:
            return self._keyword_recall(query, k, author, wave_id, source)
        return [self._mk(r, round(s, 3)) for s, r in scored]

    def _lexical(self, query: str, k: int, author, wave_id,
                 source=None) -> List[sqlite3.Row]:
        """BM25 over the same notes, same trust and status gate."""
        if not self._fts:
            return []
        terms = [t for t in re.findall(r"[\w.]{2,}", query or "")][:12]
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        sql = ("SELECT n.* FROM notes_fts f JOIN notes n ON n.id = f.rowid "
               "WHERE notes_fts MATCH ? AND n.status = 'active'"
               f" AND n.asserted_by IN ({','.join('?' * len(TRUSTED_ASSERTERS))})")
        params: List[Any] = [match, *TRUSTED_ASSERTERS]
        if author:
            sql += " AND n.author = ?"
            params.append(author)
        if wave_id:
            sql += " AND n.wave_id = ?"
            params.append(wave_id)
        if source:
            sql += " AND n.source = ?"
            params.append(source)
        sql += " ORDER BY bm25(notes_fts) LIMIT ?"
        params.append(k)
        try:
            return self.db.execute(sql, params).fetchall()
        except sqlite3.Error:
            return []

    @staticmethod
    def _rrf(rank: int, kconst: int = 60) -> float:
        return 1.0 / (kconst + rank)

    def _fuse(self, dense, lexical, k: int,
              qv: Optional[List[float]] = None) -> List["Recalled"]:
        """Reciprocal rank fusion. Rank-based, so the two score scales - cosine
        and BM25 - never have to be made commensurable."""
        scores: Dict[int, float] = {}
        rowmap: Dict[int, sqlite3.Row] = {}
        best: Dict[int, float] = {}
        for i, (sc, r) in enumerate(dense):
            scores[r["id"]] = scores.get(r["id"], 0.0) + self._rrf(i)
            rowmap[r["id"]] = r
            best[r["id"]] = sc
        for i, r in enumerate(lexical):
            scores[r["id"]] = scores.get(r["id"], 0.0) + self._rrf(i)
            rowmap.setdefault(r["id"], r)
            if r["id"] not in best:
                # Report its real similarity, not 0.0. It got here on BM25,
                # below the floor, and a reader needs to see which.
                best[r["id"]] = (_cosine(qv, _unpack(r["embedding"]))
                                 if qv and r["embedding"] else 0.0)
        order = sorted(scores, key=lambda i: scores[i], reverse=True)[:k]
        return [self._mk(rowmap[i], round(best.get(i, 0.0), 3)) for i in order]

    def _mk(self, r, score: float) -> "Recalled":
        src = self.db.execute(
            "SELECT content FROM observations WHERE drop_id=?", (r["drop_id"],)
        ).fetchone()
        return Recalled(
            text=r["text"], author=r["author"], wave_name=r["wave_name"],
            drop_id=r["drop_id"], score=score, created_at=r["created_at"],
            source=(src["content"][:400] if src and src["content"] else None),
            surface=_row_source(r),
        )

    def _keyword_recall(self, query: str, k: int, author, wave_id,
                        source=None) -> List[Recalled]:
        words = [w.lower() for w in re.findall(r"\w{4,}", query)][:8]
        if not words:
            return []
        sql = ("SELECT * FROM notes WHERE status = 'active'"
               f" AND asserted_by IN ({','.join('?' * len(TRUSTED_ASSERTERS))})"
               " AND (" + " OR ".join(
                   "LOWER(text) LIKE ?" for _ in words) + ")")
        params: List[Any] = [*TRUSTED_ASSERTERS, *(f"%{w}%" for w in words)]
        if author:
            sql += " AND author = ?"; params.append(author)
        if wave_id:
            sql += " AND wave_id = ?"; params.append(wave_id)
        if source:
            sql += " AND source = ?"; params.append(source)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(k)
        return [self._mk(r, 0.0)
                for r in self.db.execute(sql, params).fetchall()]

    def supersede(self, note_id: int, new_text: str,
                  drop_id: Optional[str] = None) -> int:
        """Replace a claim. The old row is closed, never deleted.

        Retraction is the one capability no shipping memory system enforces,
        so it is enforced here at the read boundary rather than by a flag the
        model is expected to notice.
        """
        old = self.db.execute("SELECT * FROM notes WHERE id=?",
                              (note_id,)).fetchone()
        if old is None:
            raise MemoryError_(f"no note {note_id}")
        try:
            vec = embed(contextualize(new_text, old["author"], old["wave_name"],
                                      old["created_at"]))
        except MemoryError_:
            vec = None
        now = int(time.time())
        cur = self.db.execute(
            "INSERT INTO notes(text,drop_id,wave_id,wave_name,author,kind,"
            "embedding,created_at,asserted_by,subject,status,supersedes) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,'active',?)",
            (new_text, drop_id or old["drop_id"], old["wave_id"],
             old["wave_name"], old["author"], old["kind"],
             _pack(vec) if vec else None, now, old["asserted_by"],
             old["subject"], note_id))
        self.db.execute(
            "UPDATE notes SET status='superseded', valid_to=? WHERE id=?",
            (now, note_id))
        return cur.lastrowid

    def forget(self, note_id: Optional[int] = None,
               subject: Optional[str] = None, reason: str = "") -> int:
        """Honour a retraction. Rows are closed, not removed, so the same
        claim cannot be silently re-learned from the archive."""
        now = int(time.time())
        if note_id is not None:
            cur = self.db.execute(
                "UPDATE notes SET status='revoked', valid_to=? "
                "WHERE id=? AND status!='revoked'", (now, note_id))
        elif subject:
            cur = self.db.execute(
                "UPDATE notes SET status='revoked', valid_to=? "
                "WHERE LOWER(subject)=LOWER(?) AND status!='revoked'",
                (now, subject))
        else:
            raise MemoryError_("forget needs a note_id or a subject")
        return cur.rowcount

    def about(self, author: str, k: int = 10,
              source: Optional[str] = None) -> List[Recalled]:
        """Everything learned from one person, newest first."""
        sql = ("SELECT * FROM notes WHERE LOWER(author)=LOWER(?) "
               "AND status='active' "
               f"AND asserted_by IN ({','.join('?' * len(TRUSTED_ASSERTERS))})")
        params: List[Any] = [author, *TRUSTED_ASSERTERS]
        if source:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(k)
        rows = self.db.execute(sql, params).fetchall()
        return [self._mk(r, 1.0) for r in rows]

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
            "by_surface": {
                r["source"]: {"observations": r["obs"], "notes": r["notes"]}
                for r in self.db.execute(
                    "SELECT o.source, COUNT(*) obs, "
                    "(SELECT COUNT(*) FROM notes n WHERE n.source=o.source) notes "
                    "FROM observations o GROUP BY o.source")
            },
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
