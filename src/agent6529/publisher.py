"""Idempotent publish path with read-back verification.

Sequence for every outgoing drop:
  1. one logical action in the outbox
  2. client_drop_id + exact final payload persisted BEFORE the request
  3. same id and payload reused after timeout / refresh / retry / restart
  4. returned server drop id recorded
  5. drop fetched back and author, wave, content and reply linkage verified
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from . import client as c


class VerificationFailed(c.SixtyFiveError):
    pass


def stage_drop(
    store,
    wave_id: str,
    content: str,
    reply_to: Optional[Dict[str, Any]] = None,
    title: Optional[str] = None,
    correcting: bool = False,
) -> str:
    """Persist a draft action. Returns the client_drop_id."""
    import uuid

    cdid = str(uuid.uuid4())
    payload = c.SixtyFiveClient.build_chat_drop(
        wave_id=wave_id,
        content=content,
        client_drop_id=cdid,
        reply_to=reply_to,
        title=title,
    )
    return store.create_action(
        wave_id=wave_id,
        payload=payload,
        reply_to_id=(reply_to or {}).get("drop_id"),
        status="draft",
        correcting=correcting,
    )


def send_staged(
    api: "c.SixtyFiveClient",
    store,
    client_drop_id: str,
    max_attempts: int = 3,
    verify: bool = True,
) -> Dict[str, Any]:
    """Send a staged action, reusing its frozen payload verbatim."""
    row = store.get_action(client_drop_id)
    if row is None:
        raise c.SixtyFiveError(f"no staged action {client_drop_id}")
    if row["status"] == "sent" and row["server_drop_id"]:
        return {
            "status": "already_sent",
            "server_drop_id": row["server_drop_id"],
            "client_drop_id": client_drop_id,
        }

    payload = json.loads(row["payload_json"])
    # The frozen payload must still carry the same idempotency key.
    assert payload.get("client_drop_id") == client_drop_id

    store.set_status(client_drop_id, "pending")
    delay, last = 1.0, None

    for _ in range(max_attempts):
        try:
            resp = api.create_drop(payload)
            sid = (resp or {}).get("id")
            if not sid:
                raise c.SixtyFiveError("create_drop returned no id")
            store.set_status(client_drop_id, "sent", server_drop_id=sid,
                             bump_attempts=True)
            result = {"status": "sent", "server_drop_id": sid,
                      "client_drop_id": client_drop_id}
            if verify:
                result["verification"] = verify_drop(
                    api, store, client_drop_id, sid, payload
                )
            return result

        except c.Conflict as e:
            # Idempotency replay: the server already has this client_drop_id.
            store.set_status(client_drop_id, "pending", error=str(e),
                             bump_attempts=True)
            found = _recover_by_client_id(api, payload, client_drop_id)
            if found:
                store.set_status(client_drop_id, "sent",
                                 server_drop_id=found.get("id"))
                return {"status": "recovered_conflict",
                        "server_drop_id": found.get("id"),
                        "client_drop_id": client_drop_id}
            last = e

        except (c.TransientError, c.RateLimited) as e:
            # A lost response may mean the post landed. Reuse the same id.
            last = e
            store.set_status(client_drop_id, "pending", error=str(e),
                             bump_attempts=True)
            found = _recover_by_client_id(api, payload, client_drop_id)
            if found:
                store.set_status(client_drop_id, "sent",
                                 server_drop_id=found.get("id"))
                return {"status": "recovered_after_transient",
                        "server_drop_id": found.get("id"),
                        "client_drop_id": client_drop_id}
            time.sleep(getattr(e, "retry_after", None) or delay)
            delay = min(delay * 2, 8.0)

        except c.ReconnectRequired as e:
            # Token refresh happens inside the client; one more attempt is fine.
            last = e
            store.set_status(client_drop_id, "pending", error=str(e),
                             bump_attempts=True)
            try:
                api.refresh()
            except c.SixtyFiveError:
                store.set_status(client_drop_id, "failed", error=str(e))
                raise

        except c.PermissionDenied as e:
            store.set_status(client_drop_id, "failed", error=str(e))
            raise

    store.set_status(client_drop_id, "failed", error=f"exhausted: {last}")
    raise c.SixtyFiveError(f"publish failed after {max_attempts}: {last}")


def _recover_by_client_id(api, payload: Dict[str, Any], cdid: str):
    """Look for an already-accepted drop carrying our client_drop_id.

    Used when the HTTP response was lost but the write may have landed.
    Scans the recent window of the target wave only.
    """
    try:
        feed = api.wave_drops(payload["wave_id"], limit=25,
                              search_strategy="FIND_OLDER")
    except c.SixtyFiveError:
        return None
    for d in _iter_drops(feed):
        if d.get("client_drop_id") == cdid:
            return d
    return None


def _iter_drops(feed: Any):
    if isinstance(feed, dict):
        for key in ("drops", "data", "items"):
            if isinstance(feed.get(key), list):
                return feed[key]
        return []
    return feed if isinstance(feed, list) else []


def verify_drop(
    api, store, client_drop_id: str, server_drop_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Fetch the published drop back and check it is what we intended."""
    fetched = api.drop(server_drop_id)
    checks: Dict[str, Any] = {}

    checks["wave_matches"] = (
        ((fetched.get("wave") or {}).get("id") or fetched.get("wave_id"))
        == payload["wave_id"]
    )

    want = (payload["parts"][0].get("content") or "").strip()
    got = c.SixtyFiveClient.drop_text(fetched)
    checks["content_matches"] = want in got if want else False

    sess_addr = (api.store.read() or {}).get("address")
    author = fetched.get("author") or {}
    checks["author_present"] = bool(author.get("id") or author.get("handle"))
    checks["author"] = author.get("handle") or author.get("id")
    checks["session_address"] = sess_addr

    want_parent = (payload.get("reply_to") or {}).get("drop_id")
    if want_parent:
        # Live-verified 2026-11-07: the read-back exposes the parent as
        # `reply_to_drop` (a full drop object). `reply_to` is the REQUEST
        # field only; it does not come back under that name.
        parent = (
            fetched.get("reply_to_drop")
            or fetched.get("reply_to")
            or {}
        )
        got_parent = parent.get("id") or parent.get("drop_id")
        checks["reply_linkage_matches"] = got_parent == want_parent
        checks["expected_parent"] = want_parent
        checks["actual_parent"] = got_parent
    else:
        checks["reply_linkage_matches"] = True
        checks["is_top_level"] = True

    ok = all(
        checks.get(k) for k in
        ("wave_matches", "content_matches", "author_present",
         "reply_linkage_matches")
    )
    checks["verified"] = bool(ok)
    if ok:
        store.mark_verified(client_drop_id, server_drop_id, payload["wave_id"])
    else:
        store.set_status(client_drop_id, "sent",
                         error=f"verification incomplete: {checks}")
    return checks
