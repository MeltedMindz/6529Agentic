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
import array
import math
import os
import re
import sqlite3
import struct
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from operator import mul as _mul
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
  norm        REAL,
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
    # Precomputed vector length. Recomputing it per row per query was 70% of
    # the scan; it never changes once the embedding is written.
    "ALTER TABLE notes ADD COLUMN norm REAL",
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
# `self_note` is the agent's own read of someone, which is its own memory and
# clearly attributable to itself - unlike `third_party`, a stranger's claim
# about a person, which is kept for the record and never recalled as fact.
TRUSTED_ASSERTERS = ("self", "operator", "public_post_by_self", "self_note")

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


# Bumped when the text fed to the embedder changes, because old and new
# vectors are then not comparable. `6529 reembed` rebuilds the corpus.
EMBED_VERSION = 2


def _prepare(text: str) -> str:
    """Lowercase before embedding. This is not cosmetic.

    The GGUF build of nomic-embed-text here uses the UNCASED BERT vocabulary
    but does not lowercase its input, so every token carrying a capital misses
    the vocab and becomes [UNK]. Measured on this machine: "Axiom", "Melted",
    "Soulforge", "Bankr" and a full 0x address all return the BYTE-IDENTICAL
    vector, and "Agent Tree is a paid Pro item" vs "Trace Waterfall is a paid
    Pro item" score cosine 1.000000 - two different facts, indistinguishable.
    Lowercased, that pair separates to 0.716.

    This corpus is handles, version strings and addresses, so the defect was
    hitting almost every note, and the [wave / @author / date] header added by
    contextualize() was itself almost entirely [UNK].
    """
    return (text or "")[:8000].lower()


def embed(text: str) -> List[float]:
    v = embed_many([text])
    if not v:
        raise MemoryError_("embedding model returned nothing")
    return v[0]


def embed_many(texts: List[str], keep_alive: Any = "30m") -> List[List[float]]:
    """Batch embedding. Measured here: 47 ms for one text, 12.7 ms each at a
    batch of 32, so distillation and re-embedding are several times cheaper
    in batches. /api/embed also returns L2-normalised vectors."""
    if not texts:
        return []
    payload = {"model": EMBED_MODEL, "input": [_prepare(t) for t in texts],
               "keep_alive": keep_alive}
    try:
        d = _post("/api/embed", payload)
        out = d.get("embeddings") or []
    except MemoryError_:
        out = []
    if len(out) == len(texts):
        return out
    # An older Ollama without /api/embed, or a partial reply: fall back to the
    # single-text endpoint rather than losing the batch.
    res = []
    for t in texts:
        d = _post("/api/embeddings", {"model": EMBED_MODEL, "prompt": _prepare(t)})
        v = d.get("embedding")
        if not v:
            raise MemoryError_("embedding model returned nothing")
        res.append(v)
    return res


def _pack(v: Iterable[float]) -> bytes:
    a = array.array("f", v)
    return a.tobytes()


def _unpack(b: bytes):
    """A float array, not a list. array.array avoids building 768 Python
    floats per row, which is most of the cost of scanning the corpus."""
    a = array.array("f")
    a.frombytes(b)
    return a


# math.sumprod (3.12+) is a C-level fused dot product and the single biggest
# lever in the scan. The fallback keeps the declared >=3.9 support honest.
_sumprod = getattr(math, "sumprod", None)
if _sumprod is None:                                      # pragma: no cover
    def _sumprod(a, b):
        return sum(map(_mul, a, b))


def _dot(a, b) -> float:
    return _sumprod(a, b)


def _norm(v) -> float:
    return math.sqrt(_sumprod(v, v))


def _cosine(a, b) -> float:
    if len(a) != len(b):
        return -1.0
    na, nb = _norm(a), _norm(b)
    return _dot(a, b) / (na * nb) if na and nb else -1.0


# ----------------------------------------------------------------- extraction
EXTRACT_PROMPT = """Extract durable factual claims from this forum post.

For each claim also copy the exact words from the post that support it. The
quote must appear in the post character for character; do not paraphrase it.

Rules:
- Only claims that would still be useful to know in a week.
- Each claim is one self-contained sentence, 25 to 140 characters.
- No opinions, greetings, pleasantries, or meta commentary about the post.
- Say who. The author is @{author}. When the author describes their own work,
  write "@{author}". Never write "the author", "the poster" or "the user".
- Replace relative time ("today", "tomorrow", "last week") with the actual
  date. This post was written on {date}.
- Copy names, versions, numbers and addresses exactly as written.
- A post that is only a title or a heading, with no body, contains no claims:
  return {{"claims": []}}.
- If the post contains nothing durable, return {{"claims": []}}.

Post by @{author}: "{content}"
"""

# Constrained decoding. Without a schema this model answers an ARRAY request
# with an OBJECT (its own system prompt asks for one), and the array-shaped
# regex that used to parse the reply then found nothing and returned []. That
# was a large part of a measured 70% miss rate on substantive posts.
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string", "minLength": 25,
                              "maxLength": 240},
                    "quote": {"type": "string", "maxLength": 160},
                },
                "required": ["claim", "quote"],
            },
        }
    },
    "required": ["claims"],
}


_HANDLE = re.compile(r"@\[?([A-Za-z0-9_]{2,30})\]?")


def _hash12(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


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


def _subject_of(text: str, addressing: bool = False) -> Optional[str]:
    """The person a claim is about, if it names one.

    Only an explicit @handle counts, and never one that is merely addressing.
    Guessing a subject from prose would create exactly the false
    attributions this gate exists to prevent.

    `addressing` says whether a leading @handle in this text is a reply
    prefix. See ADDRESSING_SURFACES: it is true for a message someone sent on
    a platform that opens replies that way, and false for the agent's own
    memoranda, which follow no such convention.
    """
    body = text or ""
    if addressing:
        body = _ADDRESSING.sub("", body, count=1)
    m = _HANDLE.search(body)
    return m.group(1) if m else None


def addresses_by_prefix(source: str, author: Optional[str],
                        self_handles: Iterable[str] = ()) -> bool:
    """Does a leading @handle in this text mean "to", rather than "about"?

    Only for a message written by someone else on a platform whose replies
    open that way. The agent's own notes are not replies.
    """
    if source not in ADDRESSING_SURFACES:
        return False
    a = (author or "").lower()
    return not (a and a in {h.lower() for h in self_handles})


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


def _norm_text(s: str) -> str:
    """Fold case, accents and whitespace so a quote can be compared to its
    source without tripping over "Classé" vs "Clase"."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


# Anything carrying a digit, kept whole: "rc.14", not the "14" inside it.
_IDENT_IN_CLAIM = re.compile(
    r"[0-9a-z][\w.\-]*\d[\w.\-]*|[\w.\-]+\.(?:io|com|org|net|xyz|dev)",
    re.I)


def grounded(claim: str, quote: str, source: str,
             allow: Iterable[str] = ()) -> Optional[str]:
    """Why this claim is not supported by its source, or None if it is.

    A deterministic check, no second model pass. It catches every precision
    failure measured on the live corpus: three invented "the validator
    should..." claims from a 43-character heading, a tequila misspelled from
    "Clase Azul" to "Classe Azul", and version numbers that were never in the
    post.
    """
    src = _norm_text(source)
    # The prompt asks the model to write the post's real date in place of
    # "today", so that date is legitimately absent from the source text.
    allowed = {_norm_text(a) for a in allow if a}
    q = _norm_text(quote)
    if len(q) < 8:
        return "no supporting quote"
    if q not in src:
        return "quote is not verbatim in the source"
    for ident in _IDENT_IN_CLAIM.findall(claim or ""):
        token = _norm_text(ident).rstrip(".,;:)")
        if token in allowed or any(token in a for a in allowed):
            continue
        if token not in src:
            return f"identifier not in the source: {ident}"
    # Proper nouns the model may have altered. Every capitalised word of four
    # or more characters, including the first: "Classe Azul" for the source's
    # "Clase Azul" opened the claim, and skipping sentence-initial words let
    # it through. A legitimately grounded opener is in the source anyway.
    for word in re.findall(r"\b([A-Z][a-zA-Z]{3,})\b", claim or ""):
        if _norm_text(word) not in src and _norm_text(word) not in allowed:
            return f"name not in the source: {word}"
    return None


def extract_claims(content: str, author: str, model: str = EXTRACT_MODEL,
                   max_claims: int = 8,
                   created_at: Optional[int] = None,
                   with_reasons: bool = False):
    """Pull durable claims out of a drop using the local model.

    Every claim must carry a verbatim quote from the post, and anything that
    does not survive `grounded()` is dropped before it can become memory.
    """
    content = (content or "").strip()
    if len(content) < 40:
        return ([], []) if with_reasons else []
    # think=False is load-bearing, not an optimisation. axiom-extract is built
    # on a hybrid reasoning model; Ollama routes its reasoning to a separate
    # `thinking` field, and on a real-length post it spends the entire
    # num_predict budget there and returns an EMPTY `response`. Measured on
    # backlogged observations: default -> resp=0, eval=1024, done=length, 39s.
    # With think=False -> resp=370, eval=95, done=stop, 4.4s.
    # /api/generate, not /api/chat: on this Ollama build /api/chat silently
    # ignores `format` when think is false, so the schema never constrains
    # anything.
    body = content[:12000]
    d = _post("/api/generate", {
        "model": model, "stream": False, "think": False,
        "format": EXTRACT_SCHEMA,
        "options": {"temperature": 0.0, "num_predict": 700},
        "prompt": EXTRACT_PROMPT.format(author=author or "unknown",
                                        content=body,
                                        date=_date_of(created_at)),
    })
    raw = (d.get("response") or "").strip()

    def _claims_from(blob):
        """Accept the schema's object, and a bare array from a model that
        ignored `format`. Never raise on an unexpected shape."""
        if isinstance(blob, dict):
            got = blob.get("claims")
            return got if isinstance(got, list) else []
        return blob if isinstance(blob, list) else []

    try:
        items = _claims_from(json.loads(raw))
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}|\[.*\]", raw, re.S)
        try:
            items = _claims_from(json.loads(m.group(0))) if m else []
        except json.JSONDecodeError:
            items = []

    kept: List[str] = []
    rejected: List[Dict[str, str]] = []
    seen = set()
    for it in items:
        if not isinstance(it, dict):
            continue
        claim = " ".join(str(it.get("claim") or "").split()).strip(' "')
        quote = str(it.get("quote") or "")
        # The schema asks the model for 25+ characters; this is the safety
        # net, so it is permissive on length and strict on shape. Two-word
        # fragments like "Classe Azul" are what a corpus of them looks like.
        if not (12 <= len(claim) <= 240) or len(claim.split()) < 3:
            rejected.append({"claim": claim[:80], "why": "fragment"})
            continue
        why = grounded(claim, quote, body, allow=(_date_of(created_at),))
        if why:
            rejected.append({"claim": claim[:80], "why": why})
            continue
        key = _norm_text(claim)
        if key in seen:
            continue
        seen.add(key)
        kept.append(claim)
    kept = kept[:max_claims]
    return (kept, rejected) if with_reasons else kept


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
    # This agent's own handles. Its own notes about other people are its own
    # memory, not a stranger's claim, so they stay recallable - attributed to
    # itself, never laundered into something the other person said.
    self_handles: tuple = tuple(
        h for h in os.environ.get("AGENT6529_SELF_HANDLES", "").split(",") if h
    )

    def __init__(self, path: Optional[str] = None):
        # Resolved at call time, not bound as a default: the state directory
        # can be set after this module is imported.
        path = path or DB_PATH
        self._fts = False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        # 30s of blocking retry in a cron job turns one slow writer into a
        # pile-up; 5s fails fast enough for the caller to try again later.
        self.db = sqlite3.connect(path, timeout=5.0, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        for pragma in (
            # WAL with NORMAL cannot corrupt; it can only lose the last commit
            # on power loss, which for a memory store is survivable. FULL was
            # not buying real durability here anyway: macOS needs F_FULLFSYNC
            # for that, and SQLite only issues it with PRAGMA fullfsync=1.
            "PRAGMA synchronous=NORMAL",
            "PRAGMA temp_store=MEMORY",
            "PRAGMA mmap_size=268435456",
            # Without a limit the WAL grows and never gives the space back;
            # this store was carrying a WAL larger than the database.
            "PRAGMA journal_size_limit=4194304",
        ):
            try:
                self.db.execute(pragma)
            except sqlite3.Error:
                pass            # an older build without one of these is fine
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
            missing = self.db.execute(
                "SELECT id, embedding FROM notes "
                "WHERE embedding IS NOT NULL AND norm IS NULL").fetchall()
            if missing:
                self.db.executemany(
                    "UPDATE notes SET norm=? WHERE id=?",
                    [(_norm(_unpack(r["embedding"])), r["id"]) for r in missing])
        except sqlite3.Error:
            pass                # norm is an optimisation; recall works without

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
        try:
            self.db.execute("PRAGMA optimize")
        except sqlite3.Error:
            pass
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

    def unlearned(self, limit: int = 25,
                  source: Optional[str] = None) -> List[sqlite3.Row]:
        """Observations not yet distilled. Suspicious ones are never queued.

        Oldest first, so nothing starves - but scopable by surface, because a
        caller working one surface should not have to drain another's backlog
        before reaching its own.
        """
        if limit < 0:
            raise ValueError("learning limit must be non-negative")
        sql = ("SELECT * FROM observations WHERE learned_at IS NULL "
               "AND suspicious=0")
        params: List[Any] = []
        if source:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY seen_at LIMIT ?"
        params.append(limit)
        return self.db.execute(sql, params).fetchall()

    # ---------------- learn ----------------
    @staticmethod
    def assertion_tier(author: Optional[str], subject: Optional[str],
                       operator_handles: Iterable[str] = (),
                       self_handles: Iterable[str] = ()) -> str:
        """Who is making this claim, about whom.

        A post is self-assertion when its author is also its subject, operator
        when the author is the operator, self_note when the agent is recording
        its own read of someone, and third_party otherwise. Third-party claims
        are stored but never recalled as fact.
        """
        a = (author or "").lower()
        if a and a in {h.lower() for h in operator_handles}:
            return "operator"
        if a and a in {h.lower() for h in self_handles}:
            return "self_note" if subject else "public_post_by_self"
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
                src = _row_source(row)
                subject = _subject_of(
                    text, addresses_by_prefix(src, row["author"],
                                              self.self_handles))
                tier = self.assertion_tier(row["author"], subject,
                                           self.operator_handles,
                                           self.self_handles)
                self.db.execute(
                    "INSERT INTO notes(text,drop_id,wave_id,wave_name,author,"
                    "kind,embedding,created_at,asserted_by,subject,status,"
                    "source,norm) VALUES(?,?,?,?,?,?,?,?,?,?,'active',?,?)",
                    (text, row["drop_id"], row["wave_id"], row["wave_name"],
                     row["author"], "claim",
                     _pack(vec) if vec else None, int(time.time()),
                     tier, subject, src, _norm(vec) if vec else None),
                )
                kept += 1
            except sqlite3.IntegrityError:
                pass               # same claim from the same drop already held
        self.db.execute(
            "UPDATE observations SET learned_at=? WHERE drop_id=?",
            (int(time.time()), row["drop_id"]),
        )
        return kept

    def remember(self, text: str, author: Optional[str] = None,
                 subject: Optional[str] = None, source: str = "6529",
                 drop_id: Optional[str] = None,
                 wave_id: Optional[str] = None,
                 wave_name: Optional[str] = None,
                 created_at: Optional[int] = None,
                 kind: str = "note") -> Optional[int]:
        """Store a note that is already distilled, with no model in the loop.

        An agent's own curated note must not be round-tripped through a claim
        extractor: measured on Axiom's relationship log, extraction dropped
        the handle the note was about, substituted a subject from its own
        training domain, and split one sentence into four near-duplicates.
        Text written by the agent is kept verbatim, and the subject is given
        rather than guessed.
        """
        text = (text or "").strip()
        if not text:
            return None
        try:
            vec = embed(contextualize(text, author, wave_name, created_at))
        except MemoryError_:
            vec = None
        tier = self.assertion_tier(author, subject, self.operator_handles,
                                   self.self_handles)
        try:
            cur = self.db.execute(
                "INSERT INTO notes(text,drop_id,wave_id,wave_name,author,kind,"
                "embedding,created_at,asserted_by,subject,status,source,norm) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,'active',?,?)",
                (text, drop_id or f"note-{_hash12(text)}", wave_id, wave_name,
                 author, kind, _pack(vec) if vec else None,
                 created_at or int(time.time()), tier, subject, source,
                 _norm(vec) if vec else None))
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None        # already held

    def learn_batch(self, limit: int = 25,
                    model: str = EXTRACT_MODEL,
                    source: Optional[str] = None) -> Dict[str, Any]:
        rows = self.unlearned(limit, source=source)
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
    # Measured on this corpus AFTER the lowercase fix, over 12 in-scope and 6
    # out-of-scope queries: the lowest correct answer scores 0.599, the best
    # any out-of-scope query achieves is 0.552. 0.57 sits between them.
    #
    # That gap did not exist before: while every capitalised token embedded to
    # [UNK], "what is the capital of France" scored 0.597 against a note about
    # TDH addresses, overlapping real answers. Repairing the embedder is what
    # made abstention possible at all - the floor was unreachable decoration
    # until then.
    #
    # The margin is 0.047 wide and rests on a small sample, so treat it as a
    # calibration to re-measure when the corpus changes, not a constant.
    MIN_SCORE = 0.57          # absolute floor, for abstention
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
            qn = _norm(qv) or 1.0
            for r in rows:
                v = _unpack(r["embedding"])
                nb = r["norm"] or _norm(v)
                if not nb:
                    continue
                s = _dot(qv, v) / (qn * nb)
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
        # The lexical leg exists to catch identifiers that embeddings blur -
        # rc.12 against rc.13. So it may bypass the cosine floor only when the
        # query actually contains an identifier. A plain content word matching
        # one note is not evidence, and letting those through is what made
        # this store answer "what is the best programming language".
        #
        # Without an identifier the lexical rows can still re-rank, but only
        # among notes the dense leg already admitted.
        lex = self._lexical(query, k * 2, author, wave_id, source)
        if lex and not self._has_identifier(query):
            admitted = {r["id"] for _, r in scored}
            lex = [r for r in lex if r["id"] in admitted]
        if lex:
            return self._fuse(scored, lex, k, qv)
        if not scored and not rows:
            return self._keyword_recall(query, k, author, wave_id, source)
        return [self._mk(r, round(s, 3)) for s, r in scored]

    # A term is "distinctive" if it looks like an identifier - a version, a
    # handle, an address - which is the only reason the lexical leg exists.
    # Mixed alphanumerics, or dotted/underscored/hex shapes: rc.13, v0.17,
    # 0xef2cc7d1, erc8257. A BARE number is not an identifier - "1998" in
    # "who won the 1998 world cup" is not evidence about anything here.
    _IDENTIFIERISH = re.compile(
        r"^0x[0-9a-f]+$|[a-z][0-9]|[0-9][a-z]|[._]", re.I)

    # Function words are never evidence, and a frequency gate cannot see that.
    # These notes are declarative claims, so interrogatives are RARE in them:
    # "what" and "how" both passed a 2%-of-corpus rule and let every question
    # ever asked match something. Rarity is not the same as informativeness.
    _STOPWORDS = frozenset("""
        a an and are as at be been but by can could did do does for from get
        got had has have how i if in into is it its may me might must my no
        not of on or our should so some than that the their them then there
        these they this those to use used using was we were what when where
        which who whom why will with would you your about after all any
        because before between both during each few more most other over same
        such only own too very just also like make made want need know
    """.split())
    # How common a term may be before it stops being evidence of anything.
    MAX_DF_RATIO = 0.02

    def _has_identifier(self, query: str) -> bool:
        terms = re.findall(r"[\w.]{2,}", query or "")
        return any(self._IDENTIFIERISH.search(t) for t in terms)

    def _distinctive(self, terms: List[str]) -> List[str]:
        """Drop terms that match a large share of the corpus.

        Without this, "the" matched 66 of 131 notes, so every English question
        matched something and the lexical leg answered everything. A term is
        kept when it looks like an identifier, or when it is rare enough to be
        evidence.
        """
        total = self.db.execute(
            "SELECT COUNT(*) c FROM notes WHERE status='active'").fetchone()["c"]
        if not total:
            return []
        cap = max(2, int(total * self.MAX_DF_RATIO))
        kept = []
        for t in terms:
            if self._IDENTIFIERISH.search(t):
                kept.append(t)
                continue
            if t.lower() in self._STOPWORDS or len(t) < 4:
                continue
            try:
                df = self.db.execute(
                    "SELECT COUNT(*) c FROM notes_fts WHERE notes_fts MATCH ?",
                    (f'"{t}"',)).fetchone()["c"]
            except sqlite3.Error:
                continue
            if 0 < df <= cap:
                kept.append(t)
        return kept

    def _lexical(self, query: str, k: int, author, wave_id,
                 source=None) -> List[sqlite3.Row]:
        """BM25 over the same notes, same trust and status gate."""
        if not self._fts:
            return []
        terms = [t for t in re.findall(r"[\w.]{2,}", query or "")][:12]
        terms = self._distinctive(terms)
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
                                 if qv is not None and r["embedding"] else 0.0)
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
        words = self._distinctive(words) if self._fts else words
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
            "embedding,created_at,asserted_by,subject,status,supersedes,norm,"
            "source) VALUES(?,?,?,?,?,?,?,?,?,?,'active',?,?,?)",
            (new_text, drop_id or old["drop_id"], old["wave_id"],
             old["wave_name"], old["author"], old["kind"],
             _pack(vec) if vec else None, now, old["asserted_by"],
             old["subject"], note_id, _norm(vec) if vec else None,
             _row_source(old)))
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
        # What they said, and what is trustworthily recorded about them. A
        # person's own history is both; restricting to author missed every
        # note the agent wrote about them.
        sql = ("SELECT * FROM notes WHERE "
               "(LOWER(author)=LOWER(?) OR LOWER(subject)=LOWER(?)) "
               "AND status='active' "
               f"AND asserted_by IN ({','.join('?' * len(TRUSTED_ASSERTERS))})")
        params: List[Any] = [author, author, *TRUSTED_ASSERTERS]
        if source:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(k)
        rows = self.db.execute(sql, params).fetchall()
        return [self._mk(r, 1.0) for r in rows]

    def embed_version(self) -> int:
        try:
            r = self.db.execute(
                "SELECT value FROM meta WHERE key='embed_version'").fetchone()
            return int(r["value"]) if r else 1
        except (sqlite3.Error, TypeError, ValueError):
            return 1

    def reembed(self, batch: int = 32, progress=None) -> Dict[str, Any]:
        """Rebuild every note's vector with the current recipe.

        Vectors made under different recipes are not comparable, so this is
        all-or-nothing per note and the version is only recorded once the
        whole corpus is done.
        """
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
        rows = self.db.execute(
            "SELECT id, text, author, wave_name, created_at FROM notes "
            "ORDER BY id").fetchall()
        done = failed = 0
        for i in range(0, len(rows), batch):
            chunk = rows[i:i + batch]
            texts = [contextualize(r["text"], r["author"], r["wave_name"],
                                   r["created_at"]) for r in chunk]
            try:
                vecs = embed_many(texts)
            except MemoryError_:
                failed += len(chunk)
                continue
            self.db.execute("BEGIN IMMEDIATE")
            try:
                for r, v in zip(chunk, vecs):
                    self.db.execute(
                        "UPDATE notes SET embedding=?, norm=? WHERE id=?",
                        (_pack(v), _norm(v), r["id"]))
                self.db.execute("COMMIT")
            except sqlite3.Error:
                self.db.execute("ROLLBACK")
                failed += len(chunk)
                continue
            done += len(chunk)
            if progress:
                progress(done, len(rows))
        if not failed:
            self.db.execute(
                "INSERT INTO meta(key,value) VALUES('embed_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(EMBED_VERSION),))
        return {"notes": len(rows), "reembedded": done, "failed": failed,
                "embed_version": self.embed_version(),
                "model": EMBED_MODEL}

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
            "embed_version": self.embed_version(),
            "embed_version_current": EMBED_VERSION,
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
