"""Device-key signing for 6529 writes.

A device grant lets a *separate* Ed25519 key sign your posts, so anyone can
verify a drop came from your wallet without that key ever being able to move
funds. The wallet signs the grant once (EIP-712); after that the device key
signs each write on its own.

Why an agent wants this
-----------------------
An autonomous agent posts constantly and holds a key to do it. A device key is
strictly less dangerous than a wallet key: its scopes are fixed at grant time,
it expires within 181 days, it is revocable from the 6529 UI without touching
the wallet, and the signed statement the wallet approves says in plain words
that it "can't move funds, change your handle, add devices or act as an
admin". It also makes the agent's drops independently verifiable, which
matters more for an agent than for a person.

The scheme, verified against the published contract and the reference client
(`6529-Collections/6529-core`, `renderer/lib/device-signing/`) rather than
assumed:

* The grant is EIP-712 `DeviceGrant`, domain "6529 Device Grant", version "2"
  (`uint16[] ciphersuites`) or "1" (`uint16 ciphersuite`), with a fixed salt.
  The server re-renders the statement from the fields, so the statement bytes
  must match exactly - they are a signed commitment, not UI copy.
* The grant id is the EIP-712 digest of that message, lowercase.
* Each write signs an EIP-712 `InterimEvent`, domain "6529 Network P2P"
  version "1", salt `keccak256("6529 Network pre-genesis interim 1")`. The
  Ed25519 signature is over the resulting event id.
* `bodyHash` is `keccak256` of the canonical JSON of the request body with
  `device_signature` removed; `bodySize` is that string's byte length.

Nothing here can spend. The device key signs event ids and nothing else.
"""
from __future__ import annotations

import json
import os
import secrets
import stat
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:                                    # optional: only needed to sign
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey)
    _ED25519 = True
except ImportError:                     # pragma: no cover - env dependent
    _ED25519 = False

from eth_account.messages import encode_typed_data
from eth_utils import keccak


class DeviceSigningError(Exception):
    """Something is wrong with the grant, the key, or the request."""


# ----------------------------------------------------------------- constants
GRANT_DOMAIN_V1 = {
    "name": "6529 Device Grant",
    "version": "1",
    "salt": "0x4887f15a22b96f574a9f835b87e01e293dc7587acbfc13b5f224b89cd2d8c8aa",
}
GRANT_DOMAIN_V2 = dict(GRANT_DOMAIN_V1, version="2")

GRANT_TYPES_V1 = {
    "DeviceGrant": [
        {"name": "statement", "type": "string"},
        {"name": "wallet", "type": "address"},
        {"name": "deviceKey", "type": "bytes32"},
        {"name": "scopes", "type": "string"},
        {"name": "mlsDeviceKey", "type": "bytes32"},
        {"name": "ciphersuite", "type": "uint16"},
        {"name": "issuedAt", "type": "uint64"},
        {"name": "expiresAt", "type": "uint64"},
        {"name": "origin", "type": "string"},
    ]
}
GRANT_TYPES_V2 = {
    "DeviceGrant": [
        {"name": "statement", "type": "string"},
        {"name": "wallet", "type": "address"},
        {"name": "deviceKey", "type": "bytes32"},
        {"name": "scopes", "type": "string"},
        {"name": "mlsDeviceKey", "type": "bytes32"},
        {"name": "ciphersuites", "type": "uint16[]"},
        {"name": "issuedAt", "type": "uint64"},
        {"name": "expiresAt", "type": "uint64"},
        {"name": "origin", "type": "string"},
    ]
}

EVENT_DOMAIN = {
    "name": "6529 Network P2P",
    "version": "1",
    "salt": "0x" + keccak(text="6529 Network pre-genesis interim 1").hex(),
}
EVENT_TYPES = {
    "InterimEvent": [
        {"name": "kind", "type": "uint16"},
        {"name": "kindVersion", "type": "uint16"},
        {"name": "wave", "type": "string"},
        {"name": "author", "type": "address"},
        {"name": "keyType", "type": "uint8"},
        {"name": "deviceKey", "type": "bytes32"},
        {"name": "authRef", "type": "bytes32"},
        {"name": "seq", "type": "uint64"},
        {"name": "anchor", "type": "uint64"},
        {"name": "claimedTime", "type": "uint64"},
        {"name": "refs", "type": "string[]"},
        {"name": "bodyHash", "type": "bytes32"},
        {"name": "bodySize", "type": "uint32"},
    ]
}

ZERO_HASH = "0x" + "0" * 64
ED25519_KEY_TYPE = 2
EVENT_KIND_VERSION = 1
KIND_POST, KIND_EDIT, KIND_TOMBSTONE, KIND_REACT = 1, 2, 3, 4
KIND_SCOPE = {KIND_POST: "post", KIND_EDIT: "edit",
              KIND_TOMBSTONE: "delete", KIND_REACT: "react"}

# Canonical order, and "post" is mandatory. An agent that only writes drops
# needs post and edit; delete and react cost nothing and keep the grant useful.
CANONICAL_SCOPES = ("post", "edit", "delete", "react", "vote")
DEFAULT_SCOPES = ("post", "edit", "delete", "react")

GRANT_TTL_SECONDS = 180 * 24 * 60 * 60      # the server accepts at most 181 days
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
SCOPE_NOUNS = {"post": "posts", "edit": "edits", "delete": "deletes",
               "react": "reactions", "vote": "votes"}


# ------------------------------------------------------------- canonical JSON
def canonical_json(value: Any) -> str:
    """RFC-8785-ish canonical form: keys sorted by UTF-16 code unit, no space.

    Must match the reference client byte for byte, because the hash of this
    string is inside the signature.
    """
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value or value in (
                float("inf"), float("-inf"))):
            raise DeviceSigningError("cannot canonicalize a non-finite number")
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(value.keys(), key=_utf16_key)
        return "{" + ",".join(
            f"{json.dumps(k, ensure_ascii=False)}:{canonical_json(value[k])}"
            for k in items) + "}"
    raise DeviceSigningError(f"cannot canonicalize {type(value).__name__}")


def _utf16_key(s: str):
    """Sort key matching JavaScript string comparison (UTF-16 code units)."""
    return s.encode("utf-16-be")


def canonicalize_body(body: Optional[Dict[str, Any]]) -> Tuple[Optional[str], str, int]:
    """(canonical string, bodyHash, bodySize) for a request body."""
    if body is None:
        return None, ZERO_HASH, 0
    unsigned = {k: v for k, v in body.items() if k != "device_signature"}
    canonical = canonical_json(json.loads(json.dumps(unsigned)))
    raw = canonical.encode("utf-8")
    return canonical, "0x" + keccak(raw).hex(), len(raw)


# ------------------------------------------------------------------ the key
class DeviceKey:
    """An Ed25519 signing key, kept apart from the wallet key.

    It is stored unencrypted at mode 0600 because it is a low-privilege
    credential: it can sign posts and nothing else, it expires, and it is
    revocable without touching the wallet. Treat it as a session token, not
    as a secret worth a key manager.
    """

    def __init__(self, private_bytes: bytes):
        if not _ED25519:
            raise DeviceSigningError(
                "device signing needs Ed25519: pip install cryptography")
        self._key = Ed25519PrivateKey.from_private_bytes(private_bytes)

    @classmethod
    def generate(cls) -> "DeviceKey":
        if not _ED25519:
            raise DeviceSigningError(
                "device signing needs Ed25519: pip install cryptography")
        return cls(Ed25519PrivateKey.generate().private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()))

    @property
    def public_hex(self) -> str:
        raw = self._key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        return "0x" + raw.hex()

    @property
    def private_hex(self) -> str:
        return "0x" + self._key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()).hex()

    def sign_event_id(self, event_id: str) -> str:
        """Ed25519 over the event id bytes, not over its hex text."""
        return "0x" + self._key.sign(bytes.fromhex(event_id[2:])).hex()

    def fingerprint(self) -> str:
        return key_fingerprint(self.public_hex)


def key_fingerprint(device_key_hex: str) -> str:
    """First and last eight hex characters, as the signed statement shows."""
    k = device_key_hex.lower().removeprefix("0x")
    return f"{k[:8]}...{k[-8:]}"


# ------------------------------------------------------------------ the grant
def grant_times(now: Optional[int] = None) -> Tuple[int, int]:
    """(issued_at, expires_at). Expiry is minute-aligned, as the server wants."""
    issued = int(now if now is not None else time.time())
    return issued, (issued // 60) * 60 + GRANT_TTL_SECONDS


def describe_scopes(scopes: Iterable[str]) -> str:
    nouns = [SCOPE_NOUNS.get(s, s) for s in scopes]
    if len(nouns) <= 1:
        return "".join(nouns)
    return ", ".join(nouns[:-1]) + " and " + nouns[-1]


def format_expiry(expires_at: int) -> str:
    t = time.gmtime(expires_at)
    return f"{t.tm_mday} {MONTHS[t.tm_mon - 1]} {t.tm_year}"


def render_statement(device_key_hex: str, scopes: Iterable[str],
                     expires_at: int) -> str:
    """The exact words the wallet signs.

    Byte-for-byte identical to the reference client: the server re-renders
    this from the grant fields and compares. It is a signed commitment, so it
    is never localized and never reworded.
    """
    return (
        f"Turn on signed messages on this device until "
        f"{format_expiry(expires_at)}. "
        f"This device will sign your {describe_scopes(scopes)} "
        f"so anyone can verify they came from your wallet. "
        f"It can't move funds, change your handle, add devices or act as an "
        f"admin. No transaction, no gas, no token approvals. "
        f"(Device key {key_fingerprint(device_key_hex)})"
    )


def check_scopes(scopes: Iterable[str]) -> List[str]:
    out = [s for s in CANONICAL_SCOPES if s in set(scopes)]
    unknown = sorted(set(scopes) - set(CANONICAL_SCOPES))
    if unknown:
        raise DeviceSigningError(f"unknown scope(s): {', '.join(unknown)}")
    if "post" not in out:
        raise DeviceSigningError("a grant must include the 'post' scope")
    return out


def build_grant_typed_data(wallet: str, device_key_hex: str,
                           scopes: Iterable[str], issued_at: int,
                           expires_at: int, origin: str,
                           version: int = 2) -> Dict[str, Any]:
    """The exact typed data the wallet signs. Signing-only: no MLS key."""
    if not (1 <= len(origin) <= 64) or not origin.isprintable():
        raise DeviceSigningError("origin must be 1-64 printable ASCII chars")
    if expires_at - issued_at > 181 * 24 * 60 * 60:
        raise DeviceSigningError("expiry is more than 181 days after issue")
    scopes = check_scopes(scopes)
    message = {
        "statement": render_statement(device_key_hex, scopes, expires_at),
        "wallet": wallet,
        "deviceKey": device_key_hex,
        "scopes": ",".join(scopes),
        "mlsDeviceKey": ZERO_HASH,
    }
    if version == 2:
        message["ciphersuites"] = []            # signing-only grant
        domain, types = GRANT_DOMAIN_V2, GRANT_TYPES_V2
    else:
        message["ciphersuite"] = 0
        domain, types = GRANT_DOMAIN_V1, GRANT_TYPES_V1
    message["issuedAt"] = issued_at
    message["expiresAt"] = expires_at
    message["origin"] = origin
    return {"domain": domain, "types": types,
            "primaryType": "DeviceGrant", "message": message}


def grant_id(typed_data: Dict[str, Any]) -> str:
    """The EIP-712 digest of a grant message, lowercase. This is the grant id."""
    signable = encode_typed_data(full_message=_for_eth_account(typed_data))
    return ("0x" + keccak(b"\x19\x01" + signable.header + signable.body).hex()
            ).lower()


def _for_eth_account(typed_data: Dict[str, Any]) -> Dict[str, Any]:
    """eth-account wants EIP712Domain declared in `types`."""
    domain = typed_data["domain"]
    fields = []
    for name, kind in (("name", "string"), ("version", "string"),
                       ("chainId", "uint256"), ("verifyingContract", "address"),
                       ("salt", "bytes32")):
        if name in domain:
            fields.append({"name": name, "type": kind})
    return {**typed_data, "types": {"EIP712Domain": fields, **typed_data["types"]}}


def grant_request(typed_data: Dict[str, Any], wallet_signature: str,
                  label: Optional[str] = None) -> Dict[str, Any]:
    """The POST /device-grants body for a signed grant."""
    m = typed_data["message"]
    grant: Dict[str, Any] = {
        "wallet": m["wallet"],
        "device_key": m["deviceKey"],
        "scopes": m["scopes"].split(","),
        "issued_at": m["issuedAt"],
        "expires_at": m["expiresAt"],
        "origin": m["origin"],
    }
    if "ciphersuites" in m:
        grant["version"] = 2
        grant["ciphersuites"] = list(m["ciphersuites"])
    else:
        grant["version"] = 1
        grant["ciphersuite"] = None
    body: Dict[str, Any] = {"grant": grant, "wallet_signature": wallet_signature}
    if label:
        body["device_label"] = label
    return body


# ------------------------------------------------------------------ the write
def compute_event_id(kind: int, wave: str, author: str, device_key: str,
                     auth_ref: str, seq: int, claimed_time: int,
                     body_hash: str, body_size: int,
                     refs: Optional[Iterable[str]] = None,
                     anchor: int = 0) -> str:
    """EIP-712 digest of an interim network event. This is what Ed25519 signs."""
    typed = {
        "domain": EVENT_DOMAIN, "types": EVENT_TYPES,
        "primaryType": "InterimEvent",
        "message": {
            "kind": kind, "kindVersion": EVENT_KIND_VERSION, "wave": wave,
            "author": author.lower(), "keyType": ED25519_KEY_TYPE,
            "deviceKey": device_key, "authRef": auth_ref, "seq": seq,
            "anchor": anchor, "claimedTime": claimed_time,
            "refs": list(refs or []), "bodyHash": body_hash,
            "bodySize": body_size,
        },
    }
    signable = encode_typed_data(full_message=_for_eth_account(typed))
    return "0x" + keccak(b"\x19\x01" + signable.header + signable.body).hex()


def sign_write(key: DeviceKey, grant: Dict[str, Any], wave_id: str,
               body: Dict[str, Any], seq: int, kind: int = KIND_POST,
               refs: Optional[Iterable[str]] = None,
               claimed_time_ms: Optional[int] = None) -> Dict[str, Any]:
    """Produce the `device_signature` for a write, or raise with the reason."""
    scope = KIND_SCOPE.get(kind)
    if scope not in (grant.get("scopes") or []):
        raise DeviceSigningError(
            f"this grant does not cover '{scope}'; it has "
            f"{', '.join(grant.get('scopes') or []) or 'no scopes'}")
    expires = grant.get("expires_at") or 0
    if expires and expires <= time.time():
        raise DeviceSigningError("the device grant has expired; register a new one")
    _, body_hash, body_size = canonicalize_body(body)
    # Epoch MILLISECONDS, and the server rejects more than 10 minutes of skew.
    claimed = int(claimed_time_ms if claimed_time_ms is not None
                  else time.time() * 1000)
    event_id = compute_event_id(
        kind=kind, wave=wave_id, author=grant["wallet"],
        device_key=grant["device_key"], auth_ref=grant["id"], seq=seq,
        claimed_time=claimed, body_hash=body_hash, body_size=body_size,
        refs=refs)
    return {"grant_id": grant["id"], "seq": seq, "claimed_time": claimed,
            "signature": key.sign_event_id(event_id)}


# ------------------------------------------------------------------- storage
class DeviceStore:
    """The device key, its grant, and the sequence counter.

    `seq` must be unique per device key - the server rejects a reused value -
    so it is allocated and persisted BEFORE the write goes out. A gap from an
    unused number is harmless; a repeat is not.
    """

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def read(self) -> Dict[str, Any]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def write(self, data: Dict[str, Any]) -> None:
        tmp = f"{self.path}.tmp{secrets.token_hex(4)}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)      # 0600, it holds a key
        os.replace(tmp, self.path)

    def key(self) -> Optional[DeviceKey]:
        priv = self.read().get("device_private_key")
        return DeviceKey(bytes.fromhex(priv[2:])) if priv else None

    def ensure_key(self) -> DeviceKey:
        existing = self.key()
        if existing:
            return existing
        key = DeviceKey.generate()
        data = self.read()
        data["device_private_key"] = key.private_hex
        data["device_key"] = key.public_hex
        self.write(data)
        return key

    def grant(self) -> Optional[Dict[str, Any]]:
        return self.read().get("grant")

    def save_grant(self, grant: Dict[str, Any]) -> None:
        data = self.read()
        data["grant"] = grant
        data.setdefault("seq", 0)
        self.write(data)

    def next_seq(self) -> int:
        """Allocate and persist the next sequence number before it is used."""
        data = self.read()
        seq = int(data.get("seq") or 0) + 1
        data["seq"] = seq
        self.write(data)
        return seq

    def forget_grant(self) -> None:
        data = self.read()
        data.pop("grant", None)
        self.write(data)
