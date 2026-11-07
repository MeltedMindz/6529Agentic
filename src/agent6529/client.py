"""6529.io API client for Axiom (native session-v2).

Contract and the two resolved spec defects are documented in contract.md
(retrieved 2026-11-07 from https://api.6529.io/openapi.json).

Design rules enforced here:
  * The exact `signable_message` bytes from the server are signed. Never
    normalised, re-encoded, or reconstructed.
  * Private key material is read from Keychain at the moment of signing, used,
    and dropped. It is never returned, logged, stored, or interpolated into a
    message or error.
  * Refresh tokens rotate. Rotation is atomic (tmp + os.replace under a file
    lock) so a cron process and an interactive process cannot corrupt the
    stored session.
  * `refresh_request_id` is persisted *before* the refresh call so an
    interrupted refresh can recover the already-rotated session.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

BASE_URL = os.environ.get("AGENT6529_API_BASE", "https://api.6529.io/api")
CLIENT_TYPE = "native"
USER_AGENT = os.environ.get("AGENT6529_USER_AGENT", "6529-agent/0.1")
DEFAULT_TIMEOUT = 30

STATE_DIR = os.path.expanduser(
    os.environ.get("AGENT6529_STATE_DIR", "~/.6529")
)
SESSION_PATH = os.path.join(STATE_DIR, "session.json")
LOCK_PATH = os.path.join(STATE_DIR, "session.lock")

# Secrets that may be referenced. Values are never printed.
REDACT_KEYS = {
    "access_token",
    "native_refresh_token",
    "client_signature",
    "server_signature",
    "signature",
    "private_key",
}


class SixtyFiveError(Exception):
    """Base error. Message text is always redaction-safe."""


class AuthError(SixtyFiveError):
    """Authentication or session problem. Needs reconnect."""


class ReconnectRequired(AuthError):
    """Session is expired or revoked; a fresh wallet signature is needed."""


class PermissionDenied(SixtyFiveError):
    """403 / ineligible. A clear status, never something to bypass."""


class Conflict(SixtyFiveError):
    """409 — typically idempotency replay."""


class RateLimited(SixtyFiveError):
    def __init__(self, msg: str, retry_after: Optional[float] = None):
        super().__init__(msg)
        self.retry_after = retry_after


class TransientError(SixtyFiveError):
    """5xx / network. Retryable within bounds."""


def redact(obj: Any) -> Any:
    """Deep-copy a structure with secret-bearing values replaced."""
    if isinstance(obj, dict):
        return {
            k: ("<redacted>" if k in REDACT_KEYS else redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str) and len(obj) > 120:
        return obj[:60] + f"...<truncated {len(obj)}>"
    return obj


# --------------------------------------------------------------------------
# Signer
# --------------------------------------------------------------------------
@dataclass
class KeychainSigner:
    """EIP-191 personal_sign using a key held in the macOS Keychain.

    `address` is recorded at construction so callers can assert the expected
    identity *before* any network call. The key itself is fetched only inside
    sign() and dropped immediately.
    """

    service: str
    account: str = "axiom"
    _address: Optional[str] = field(default=None, repr=False)

    def _read_key(self) -> str:
        for args in (
            ["-a", self.account, "-s", self.service, "-w"],
            ["-s", self.service, "-w"],
        ):
            r = subprocess.run(
                ["security", "find-generic-password", *args],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if r.returncode == 0 and r.stdout.strip():
                k = r.stdout.strip()
                return k if k.startswith("0x") else "0x" + k
        raise SixtyFiveError(f"keychain entry not found: {self.service}")

    @property
    def address(self) -> str:
        if self._address is None:
            from eth_account import Account

            key = self._read_key()
            try:
                self._address = Account.from_key(key).address
            finally:
                del key
        return self._address

    def sign_message_exact(self, signable_message: str) -> str:
        """personal_sign over the exact server-provided string.

        The message is encoded with EIP-191 `encode_defunct` as-is. No strip(),
        no unicode normalisation, no reconstruction from parts.
        """
        from eth_account import Account
        from eth_account.messages import encode_defunct

        key = self._read_key()
        try:
            encoded = encode_defunct(text=signable_message)
            return Account.sign_message(encoded, private_key=key).signature.hex()
        finally:
            del key


@dataclass
class BankrSigner:
    """EIP-191 personal_sign via the Bankr CLI.

    The private key is held by Bankr and never exists on this machine, so
    there is no key on disk to read, log, or leak. The signature is recovered
    locally and checked against the expected address before it is sent.

    Note on wallet kind: an EOA carrying an EIP-7702 delegation on one chain
    still has no code on another. If the auth challenge names a chain where
    the address has no code, it verifies as a plain EOA signature and
    wallet_kind_hint stays "eoa". Check before assuming.
    """

    address: str = ""          # set it explicitly; there is no default
    bankr_bin: str = "/opt/homebrew/bin/bankr"
    timeout: int = 180

    # Addresses this signer must never act for. Populate with any wallet
    # that has been rotated out or whose key is no longer trusted.
    denylist: tuple = ()

    def __post_init__(self):
        if not self.address:
            raise SixtyFiveError(
                "BankrSigner needs an explicit address; refusing to guess one"
            )
        if self.address.lower() in {d.lower() for d in self.denylist}:
            raise SixtyFiveError(
                f"refusing to sign with denylisted wallet {self.address}"
            )

    def sign_message_exact(self, signable_message: str) -> str:
        """Sign the exact server string. No normalisation of any kind."""
        r = subprocess.run(
            [self.bankr_bin, "wallet", "sign",
             "--type", "personal_sign",
             "--message", signable_message],
            capture_output=True, text=True, timeout=self.timeout,
        )
        if r.returncode != 0:
            raise SixtyFiveError(f"bankr sign failed (rc={r.returncode})")
        out = r.stdout or ""
        m = re.search(r"Signature:\s*(0x[0-9a-fA-F]{130,132})", out)
        if not m:
            raise SixtyFiveError("bankr sign returned no signature")
        sig = m.group(1)
        who = re.search(r"Signer:\s*(0x[0-9a-fA-F]{40})", out)
        if who and who.group(1).lower() != self.address.lower():
            raise SixtyFiveError(
                f"bankr signed as {who.group(1)}, expected {self.address}"
            )
        # Prove locally that the signature matches the message and address
        # before it is sent anywhere.
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct

            rec = Account.recover_message(
                encode_defunct(text=signable_message), signature=sig
            )
            if rec.lower() != self.address.lower():
                raise SixtyFiveError(
                    f"signature recovers to {rec}, expected {self.address}"
                )
        except ImportError:
            pass  # recovery check is best-effort
        return sig


# --------------------------------------------------------------------------
# Session storage (atomic, cross-process)
# --------------------------------------------------------------------------
class SessionStore:
    def __init__(self, path: str = SESSION_PATH, lock_path: str = LOCK_PATH):
        self.path = path
        self.lock_path = lock_path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _lock(self):
        import fcntl

        fh = open(self.lock_path, "a+")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        return fh

    def read(self) -> Dict[str, Any]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def write(self, data: Dict[str, Any]) -> None:
        """Atomic replace so a concurrent reader never sees a partial file."""
        tmp = f"{self.path}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)
        os.chmod(self.path, 0o600)

    def update(self, **fields) -> Dict[str, Any]:
        with self._lock():
            cur = self.read()
            cur.update(fields)
            self.write(cur)
            return cur

    def clear(self) -> None:
        with self._lock():
            if os.path.exists(self.path):
                os.remove(self.path)


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------
class SixtyFiveClient:
    def __init__(
        self,
        signer: Optional[KeychainSigner] = None,
        base_url: str = BASE_URL,
        store: Optional[SessionStore] = None,
        timeout: int = DEFAULT_TIMEOUT,
        transport=None,
    ):
        self.signer = signer
        self.base_url = base_url.rstrip("/")
        self.store = store or SessionStore()
        self.timeout = timeout
        # transport(method, url, headers, body) -> (status, headers, text)
        self._transport = transport or self._urllib_transport

    # ---------------- transport ----------------
    def _urllib_transport(self, method, url, headers, body):
        data = body.encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers or {}), e.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            raise TransientError(f"network: {type(e).__name__}") from None

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        auth: bool = True,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if auth:
            headers["Authorization"] = f"Bearer {self._access_token()}"

        status, resp_headers, text = self._transport(
            method, url, headers, json.dumps(body) if body is not None else None
        )
        return self._handle(status, resp_headers, text, method, path)

    def _read(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """GET a public read route, degrading to anonymous when unauthenticated.

        6529 serves public Waves and drops without a session, so `observe`
        mode stays useful before onboarding completes. Authenticated reads are
        preferred because viewer-specific fields (chat eligibility, viewer
        context) are only populated for a logged-in viewer.
        """
        try:
            return self._request("GET", path, params=params, auth=True)
        except ReconnectRequired:
            return self._request("GET", path, params=params, auth=False)

    def _handle(self, status, headers, text, method, path):
        if 200 <= status < 300:
            if not text.strip():
                return None
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        detail = text[:300]
        if status == 401:
            raise ReconnectRequired(f"401 on {method} {path}: {detail}")
        if status == 403:
            raise PermissionDenied(f"403 on {method} {path}: {detail}")
        if status == 409:
            raise Conflict(f"409 on {method} {path}: {detail}")
        if status == 429:
            ra = headers.get("Retry-After") or headers.get("retry-after")
            try:
                retry_after = float(ra) if ra is not None else None
            except (TypeError, ValueError):
                retry_after = None
            raise RateLimited(f"429 on {method} {path}", retry_after)
        if status >= 500:
            raise TransientError(f"{status} on {method} {path}: {detail}")
        raise SixtyFiveError(f"{status} on {method} {path}: {detail}")

    # ---------------- auth ----------------
    def _access_token(self) -> str:
        s = self.store.read()
        tok = s.get("access_token")
        exp = s.get("access_token_expires_at")
        if not tok:
            raise ReconnectRequired("no stored session; run `connect`")
        if self._expired(exp, skew=60):
            self.refresh()
            tok = self.store.read().get("access_token")
            if not tok:
                raise ReconnectRequired("refresh produced no access token")
        return tok

    @staticmethod
    def _expired(ts: Any, skew: int = 0) -> bool:
        if ts is None:
            return True
        epoch = _to_epoch(ts)
        if epoch is None:
            return True
        return time.time() + skew >= epoch

    def session_nonce(self, signer_address: str, chain_id: Optional[int] = None):
        return self._request(
            "GET",
            "/auth/session-nonce",
            params={
                "signer_address": signer_address,
                "client_type": CLIENT_TYPE,
                "chain_id": chain_id,
            },
            auth=False,
        )

    @staticmethod
    def validate_challenge(
        challenge: Dict[str, Any],
        expected_address: str,
        expect_service: str = "6529",
        expected_chain_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Validate the challenge before signing anything.

        Checks the message actually references this service and this wallet,
        is not already expired, and does not name a different auth chain than
        the one we believe we can satisfy. Raises AuthError on mismatch.
        """
        if not isinstance(challenge, dict):
            raise AuthError("challenge is not an object")
        msg = challenge.get("signable_message")
        srv = challenge.get("server_signature")
        if not msg or not isinstance(msg, str):
            raise AuthError("challenge missing signable_message")
        if not srv or not isinstance(srv, str):
            raise AuthError("challenge missing server_signature")

        low = msg.lower()
        if expect_service and expect_service.lower() not in low:
            raise AuthError(
                f"challenge does not reference expected service {expect_service!r}"
            )
        if expected_address.lower() not in low:
            raise AuthError("challenge does not reference the expected wallet")

        # Expiry, if the message carries one.
        for line in msg.splitlines():
            key = line.split(":", 1)[0].strip().lower()
            if key in ("expiration time", "expires at", "expiry"):
                val = line.split(":", 1)[1].strip()
                epoch = _to_epoch(val)
                if epoch is not None and epoch <= time.time():
                    raise AuthError("challenge already expired")
            if key in ("chain id", "chain_id") and expected_chain_id is not None:
                digits = "".join(c for c in line.split(":", 1)[1] if c.isdigit())
                if digits and int(digits) != expected_chain_id:
                    raise AuthError(
                        f"challenge chain id {digits} != expected "
                        f"{expected_chain_id}; signer may not be able to verify "
                        "on that chain"
                    )
        return {"signable_message": msg, "server_signature": srv}

    def connect(
        self,
        chain_id: Optional[int] = None,
        expected_address: Optional[str] = None,
        wallet_kind_hint: str = "eoa",
        signature_version: Optional[int] = None,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Full session-v2 login. `role` stays None for Axiom's own account."""
        if self.signer is None:
            raise AuthError("no signer configured")
        addr = self.signer.address
        if expected_address and addr.lower() != expected_address.lower():
            raise AuthError(
                f"signer address {addr} != expected {expected_address}; refusing"
            )

        challenge = self.validate_challenge(
            self.session_nonce(addr, chain_id=chain_id),
            expected_address=addr,
            expected_chain_id=chain_id,
        )
        sig = self.signer.sign_message_exact(challenge["signable_message"])
        body = {
            "client_type": CLIENT_TYPE,
            "client_address": addr,
            "client_signature": sig if sig.startswith("0x") else "0x" + sig,
            "server_signature": challenge["server_signature"],
            "wallet_kind_hint": wallet_kind_hint,
        }
        if signature_version is not None:
            body["signature_version"] = signature_version
        if role is not None:  # proxy acting-as; omitted for Axiom's own account
            body["role"] = role

        resp = self._request("POST", "/auth/session-login", body=body, auth=False)
        return self._persist_session(resp, addr)

    def _persist_session(self, resp: Dict[str, Any], addr: str) -> Dict[str, Any]:
        if not isinstance(resp, dict) or not resp.get("access_token"):
            raise AuthError("login/refresh response missing access_token")
        if resp.get("address") and resp["address"].lower() != addr.lower():
            raise AuthError(
                f"server bound session to {resp['address']} not {addr}; refusing"
            )
        self.store.update(
            address=resp.get("address", addr),
            role=resp.get("role"),
            access_token=resp["access_token"],
            access_token_expires_at=resp.get("access_token_expires_at"),
            native_refresh_token=resp.get("native_refresh_token"),
            refresh_token_expires_at=resp.get("refresh_token_expires_at"),
            client_type=resp.get("client_type", CLIENT_TYPE),
            connected_at=int(time.time()),
            refresh_request_id=None,
        )
        return redact(resp)

    def refresh(self, max_attempts: int = 3) -> Dict[str, Any]:
        """Rotate the session.

        A `refresh_request_id` is persisted *before* the call. If the response
        is lost, the retry reuses the same id with the same refresh token and
        the server returns the already-rotated session instead of rejecting it.
        """
        # The lock is held only to read state and stamp refresh_request_id.
        # It is deliberately released before the network call: _persist_session
        # re-acquires it to write, and holding it across I/O would deadlock.
        with self.store._lock():
            s = self.store.read()
            addr = s.get("address")
            rt = s.get("native_refresh_token")
            if not addr or not rt:
                raise ReconnectRequired("no refresh token stored; run `connect`")
            if self._expired(s.get("refresh_token_expires_at")):
                raise ReconnectRequired("refresh token expired; run `connect`")

            # Persisted BEFORE the call so an interrupted refresh can recover
            # the already-rotated session by reusing this id.
            req_id = s.get("refresh_request_id") or str(uuid.uuid4())
            if s.get("refresh_request_id") != req_id:
                s["refresh_request_id"] = req_id
                self.store.write(s)

        body = {
            "client_type": CLIENT_TYPE,
            "client_address": addr,
            "native_refresh_token": rt,
            "refresh_request_id": req_id,
        }
        delay = 1.0
        last: Optional[Exception] = None
        for _ in range(max_attempts):
            try:
                resp = self._request(
                    "POST", "/auth/session-refresh", body=body, auth=False
                )
                return self._persist_session(resp, addr)
            except (TransientError, RateLimited) as e:
                last = e
                time.sleep(getattr(e, "retry_after", None) or delay)
                delay = min(delay * 2, 8.0)
            except ReconnectRequired:
                raise
        raise TransientError(f"refresh failed after {max_attempts} attempts: {last}")

    def logout(self, all_sessions: bool = False) -> None:
        """Scoped logout. Never revokes every wallet session by default."""
        s = self.store.read()
        addr, rt = s.get("address"), s.get("native_refresh_token")
        if addr and rt:
            try:
                self._request(
                    "POST",
                    "/auth/session-logout",
                    body={
                        "client_type": CLIENT_TYPE,
                        "client_address": addr,
                        "native_refresh_token": rt,
                        "all_sessions": all_sessions,
                    },
                    auth=False,
                )
            except SixtyFiveError:
                pass  # local teardown proceeds regardless
        self.store.clear()

    def auth_status(self) -> Dict[str, Any]:
        s = self.store.read()
        if not s:
            return {"connected": False, "reason": "no session stored"}
        return {
            "connected": not self._expired(s.get("access_token_expires_at")),
            "address": s.get("address"),
            "role": s.get("role"),
            "acting_as_self": s.get("role") in (None, ""),
            "access_token_expires_at": s.get("access_token_expires_at"),
            "refresh_token_expires_at": s.get("refresh_token_expires_at"),
            "refresh_in_flight": bool(s.get("refresh_request_id")),
        }

    # ---------------- identity ----------------
    def identity_by_wallet(self, wallet: str) -> Dict[str, Any]:
        return self._request(
            "GET", f"/identities/by-wallet/{wallet}", auth=False
        )

    @staticmethod
    def is_placeholder_identity(ident: Dict[str, Any]) -> bool:
        """True when the lookup returned a stub rather than a real profile."""
        if not isinstance(ident, dict):
            return True
        handle = ident.get("handle")
        if not handle:
            return True
        addr = (ident.get("primary_wallet") or "").lower()
        return handle.lower() == f"id-{addr}" or ident.get("id") in (None, "")

    # ---------------- waves ----------------
    def waves(self, view: str = "HOT", name=None, page=1, page_size=20,
              followed_only=None, overview_type=None) -> Any:
        # Live-verified 2026-11-07: view=OVERVIEW is rejected with
        # '"overview_type" is required'. Supply a default rather than 400.
        if view == "OVERVIEW" and not overview_type:
            overview_type = "RECENTLY_DROPPED_TO"
        return self._read(
            "/v2/waves",
            params={
                "view": view,
                "name": name,
                "page": page,
                "page_size": page_size,
                "only_waves_followed_by_authenticated_user": followed_only,
                "overview_type": overview_type,
            },
        )

    def wave(self, wave_id: str) -> Dict[str, Any]:
        return self._read(f"/waves/{wave_id}")

    def wave_drops(self, wave_id, limit=20, serial_no_limit=None,
                   search_strategy="FIND_OLDER", drop_type=None) -> Any:
        return self._read(
            f"/v2/waves/{wave_id}/drops",
            params={
                "limit": limit,
                "serial_no_limit": serial_no_limit,
                "search_strategy": search_strategy,
                "drop_type": drop_type,
            },
        )

    def drop(self, drop_id: str) -> Dict[str, Any]:
        """Fetch one drop.

        Live-verified 2026-11-07: GET /v2/drops/{id} returns a
        {"drop": {...}, "wave": {...}} envelope, not a bare drop. The wave is
        folded in so callers see one flat object.
        """
        raw = self._read(f"/v2/drops/{drop_id}")
        if isinstance(raw, dict) and "drop" in raw and isinstance(raw["drop"], dict):
            d = dict(raw["drop"])
            if raw.get("wave") and not d.get("wave"):
                d["wave"] = raw["wave"]
            return d
        return raw

    @staticmethod
    def drop_text(drop: Dict[str, Any]) -> str:
        """Extract body text across both live shapes.

        Live-verified 2026-11-07: the wave-drops LIST endpoint returns
        `parts: null` with a flat top-level `content` string, while the
        create/verify path uses `parts[].content`. Both are handled.
        """
        if not isinstance(drop, dict):
            return ""
        parts = drop.get("parts")
        if isinstance(parts, list) and parts:
            return " ".join(
                (p.get("content") or "") for p in parts if isinstance(p, dict)
            ).strip()
        content = drop.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, dict):
            return (content.get("text") or content.get("content") or "").strip()
        return ""

    def drop_replies(self, drop_id, limit=20, serial_no_limit=None,
                     search_strategy="FIND_OLDER") -> Any:
        return self._read(
            f"/v2/drops/{drop_id}/replies",
            params={
                "limit": limit,
                "serial_no_limit": serial_no_limit,
                "search_strategy": search_strategy,
            },
        )

    def notifications(self, limit=20, id_less_than=None, unread_only=None,
                      cause=None) -> Any:
        return self._request(
            "GET",
            "/v2/notifications",
            params={
                "limit": limit,
                "id_less_than": id_less_than,
                "unread_only": unread_only,
                "cause": cause,
            },
        )

    # ---------------- eligibility ----------------
    @staticmethod
    def chat_eligibility(wave: Dict[str, Any], is_reply: bool = False) -> Dict[str, Any]:
        """Derive a clear postability verdict. Missing permission is a status."""
        chat = (wave or {}).get("chat") or {}
        reasons: List[str] = []

        if not chat.get("enabled", False):
            reasons.append("chat_disabled")
        if is_reply:
            replies = chat.get("replies") or {}
            # Reply permission is tracked separately from top-level chat.
            if replies.get("enabled") is False:
                reasons.append("replies_disabled")
            elig = replies.get("authenticated_user_eligible")
            if elig is None:
                elig = chat.get("authenticated_user_eligible")
            if elig is False:
                reasons.append("not_eligible_to_reply")
        else:
            if chat.get("authenticated_user_eligible") is False:
                reasons.append("not_eligible_to_chat")

        now_ms = int(time.time() * 1000)
        next_allowed = chat.get("next_drop_allowed")
        if isinstance(next_allowed, (int, float)) and next_allowed > now_ms:
            reasons.append("slow_mode_cooldown")

        for p in (wave or {}).get("pauses") or []:
            if isinstance(p, dict) and p.get("active", True):
                reasons.append("wave_paused")
                break

        return {
            "eligible": not reasons,
            "reasons": reasons,
            "links_disabled": bool(chat.get("links_disabled")),
            "next_drop_allowed": next_allowed,
            "slow_mode_cooldown_ms": chat.get("slow_mode_cooldown_ms"),
            "signature_required": bool(
                ((wave or {}).get("participation") or {}).get("signature_required")
            ),
        }

    # ---------------- writes ----------------
    @staticmethod
    def build_chat_drop(
        wave_id: str,
        content: str,
        client_drop_id: str,
        reply_to: Optional[Dict[str, Any]] = None,
        title: Optional[str] = None,
        hide_link_preview: bool = False,
    ) -> Dict[str, Any]:
        """Build an ordinary CHAT drop payload.

        Uses `drop_type` (not the stale `type` in the spec's required list).
        Omits `signature` and `device_signature` entirely — see contract.md.
        """
        if not content or not content.strip():
            raise SixtyFiveError("drop content is empty")
        payload: Dict[str, Any] = {
            "wave_id": wave_id,
            "drop_type": "CHAT",
            "client_drop_id": client_drop_id,
            "parts": [{"content": content, "media": []}],
            "referenced_nfts": [],
            "mentioned_users": [],
            "metadata": [],
        }
        if title:
            payload["title"] = title
        if hide_link_preview:
            payload["hide_link_preview"] = True
        if reply_to:
            if not reply_to.get("drop_id") or reply_to.get("drop_part_id") is None:
                raise SixtyFiveError("reply_to needs drop_id and drop_part_id")
            payload["reply_to"] = {
                "drop_id": reply_to["drop_id"],
                "drop_part_id": int(reply_to["drop_part_id"]),
            }
        return payload

    def create_drop(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/drops", body=payload)


def _to_epoch(ts: Any) -> Optional[float]:
    """Accept epoch seconds, epoch millis, or ISO-8601."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts) / 1000.0 if ts > 1e11 else float(ts)
    if isinstance(ts, str):
        t = ts.strip()
        if t.isdigit():
            v = float(t)
            return v / 1000.0 if v > 1e11 else v
        try:
            from datetime import datetime

            return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None
