"""Validator management for agents.

Wraps the official 6529 `validator` binary and its signed release feed so an
agent can install, monitor and upgrade a validator without a browser.

Two deliberate boundaries:

  * **Install is never automatic.** The project ships no auto-updates on
    purpose (P36). `check_release()` tells you an upgrade is due; it does not
    perform one. `plan_upgrade()` prints the steps for a human or a supervised
    run to execute.
  * **Downloads are always verified.** `download_release()` refuses to return a
    path whose SHA-256 does not match the signed feed.

The one step that genuinely needs a wallet is the grant. It is EIP-712 typed
data, so it can be signed headlessly by any signer that supports
`eth_signTypedData_v4` — see `grant_draft()` / `grant_import()`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

FEED_URL = os.environ.get(
    "AGENT6529_VALIDATOR_FEED", "https://6529.io/validator/releases.json"
)
DOWNLOAD_BASE = os.environ.get(
    "AGENT6529_VALIDATOR_DOWNLOAD", "https://6529.io/validator/download"
)
VALIDATOR_BIN = os.environ.get("AGENT6529_VALIDATOR_BIN", "validator")

# Exit codes documented in docs/install/operations.md ("For a watchdog").
EXIT_OK = 0          # running, nothing needs you
EXIT_ATTENTION = 5   # running, an open AL1/AL2/AL3 alert or a missing key/grant
EXIT_STOPPED = 3     # not running


class ValidatorError(Exception):
    pass


# ---------------------------------------------------------------- release feed
def fetch_feed(url: str = FEED_URL, timeout: int = 30) -> Dict[str, Any]:
    """Fetch the signed release feed.

    The signature (`releases.json.sig`) is verified by the validator itself
    against a key baked into every release. This client does not re-implement
    that check, so treat the feed as advisory for *scheduling* and always
    verify the artifact SHA-256 before running anything.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "agent6529/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def target_triple(machine: Optional[str] = None,
                  system: Optional[str] = None) -> str:
    """Map the host to the release's target triple."""
    import platform

    m = (machine or platform.machine()).lower()
    s = (system or platform.system()).lower()
    arch = "aarch64" if m in ("arm64", "aarch64") else "x86_64"
    if s == "darwin":
        return f"{arch}-apple-darwin"
    if s == "windows":
        return f"{arch}-pc-windows-msvc"
    return f"{arch}-unknown-linux-gnu"


def installed_version(binary: str = VALIDATOR_BIN) -> Optional[str]:
    """`validator --version` -> '0.1.0-rc.10', or None if not installed."""
    exe = shutil.which(binary) or binary
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True,
                           timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    # "validator 0.1.0-rc.10 (f0a3440, TDH v1.4)"
    parts = (r.stdout or "").split()
    return parts[1] if len(parts) > 1 else None


def _ver_key(v: str):
    """Order 0.1.0 < 0.1.0-rc.9 < 0.1.0-rc.10 sensibly enough to compare."""
    base, _, rc = (v or "").partition("-rc.")
    nums = []
    for p in base.split("."):
        nums.append(int(p) if p.isdigit() else 0)
    # a release with no -rc is newer than its own rc line
    return (tuple(nums), 1 if not rc else 0, int(rc) if rc.isdigit() else 0)


@dataclass
class ReleaseStatus:
    installed: Optional[str]
    latest: Optional[str]
    min_supported: Optional[str]
    deadline: Optional[str]
    deadline_reason: Optional[str]
    sequence: Optional[int]
    upgrade_available: bool
    below_min_supported: bool
    # Per-release urgency. A release can be urgent while the installed version
    # is still at or above min_supported, so comparing versions alone misses
    # it - which is exactly what happened with rc.12 on 2026-11-08.
    severity: Optional[str] = None
    severity_reason: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()

    @property
    def urgent(self) -> bool:
        """Urgent means act now, from either signal.

        Below min_supported stops signatures counting. A release flagged
        urgent/critical can matter just as much while the installed version is
        still technically supported.
        """
        sev = (self.severity or "").lower()
        return self.below_min_supported or sev in ("urgent", "critical", "high")


def check_release(binary: str = VALIDATOR_BIN,
                  feed: Optional[Dict[str, Any]] = None) -> ReleaseStatus:
    """Compare the installed version against the feed. Changes nothing."""
    d = feed if feed is not None else fetch_feed()
    rels: List[Dict[str, Any]] = d.get("releases") or []
    latest = rels[0].get("version") if rels else None
    minsup = d.get("min_supported")
    inst = installed_version(binary)

    upgrade = bool(inst and latest and _ver_key(inst) < _ver_key(latest))
    below = bool(inst and minsup and _ver_key(inst) < _ver_key(minsup))

    # Carry the newest release's own severity when we are not yet on it.
    sev = sev_reason = None
    if rels and upgrade:
        sev = rels[0].get("severity")
        sev_reason = rels[0].get("reason") or rels[0].get("notes")

    return ReleaseStatus(
        installed=inst, latest=latest, min_supported=minsup,
        deadline=d.get("deadline"), deadline_reason=d.get("deadline_reason"),
        sequence=d.get("sequence"),
        upgrade_available=upgrade, below_min_supported=below,
        severity=sev, severity_reason=sev_reason,
    )


def release_files(version: str,
                  feed: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    d = feed if feed is not None else fetch_feed()
    for r in d.get("releases") or []:
        if r.get("version") == version:
            return r.get("files") or []
    raise ValidatorError(f"version {version} not in feed")


def download_release(version: str, dest_dir: str,
                     triple: Optional[str] = None,
                     feed: Optional[Dict[str, Any]] = None,
                     timeout: int = 600) -> str:
    """Download the tarball for this host and verify its SHA-256.

    Raises if the digest does not match the feed. Never returns an unverified
    path — an unverified build must not be run.
    """
    d = feed if feed is not None else fetch_feed()
    triple = triple or target_triple()
    files = release_files(version, d)
    ext = ".zip" if "windows" in triple else ".tar.gz"
    name = next(
        (f["name"] for f in files
         if triple in f.get("name", "") and f.get("name", "").endswith(ext)),
        None,
    )
    if not name:
        raise ValidatorError(f"no artifact for {triple} in {version}")
    want = next(f["sha256"] for f in files if f["name"] == name)

    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, name)
    url = f"{DOWNLOAD_BASE}/{version}/{name}"
    req = urllib.request.Request(url, headers={"User-Agent": "agent6529/0.1"})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=timeout) as r, open(path, "wb") as fh:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            h.update(chunk)
    got = h.hexdigest()
    if got != want:
        os.remove(path)
        raise ValidatorError(
            f"checksum mismatch for {name}: got {got}, feed says {want}"
        )
    return path


def plan_upgrade(status: ReleaseStatus, triple: Optional[str] = None) -> List[str]:
    """Human-readable upgrade steps. Deliberately does not execute them."""
    if not status.latest:
        return ["no release information"]
    t = triple or target_triple()
    v = status.latest
    base = "0.1.0"  # artifact file version, distinct from the release tag
    if "darwin" in t:
        root, svc = "/usr/local/6529-validator", \
            "sudo launchctl kickstart -k system/io.6529.validator"
    else:
        root, svc = "/opt/6529-validator", \
            "sudo systemctl restart 6529-validator"
    return [
        f"download validator-{base}-{t}.tar.gz for {v} and verify its SHA-256",
        f"tar -xzf validator-{base}-{t}.tar.gz",
        f"sudo cp -R validator-{base}-{t} {root}/",
        f"sudo ln -sfn {root}/validator-{base}-{t}/validator /usr/local/bin/validator",
        svc,
        "validator --version   # confirm",
        "keep the previous folder until the new one has signed a day",
    ]


# ---------------------------------------------------------------- local control
def _run(args: List[str], data_dir: Optional[str] = None,
         binary: str = VALIDATOR_BIN, timeout: int = 120) -> subprocess.CompletedProcess:
    exe = shutil.which(binary) or binary
    cmd = [exe] + args
    if data_dir:
        cmd += ["--data-dir", data_dir]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def status(data_dir: Optional[str] = None, binary: str = VALIDATOR_BIN,
           as_json: bool = True) -> Dict[str, Any]:
    """Run `validator status` and interpret the documented exit codes."""
    args = ["status"] + (["--json"] if as_json else [])
    r = _run(args, data_dir, binary)
    meaning = {
        EXIT_OK: "running, nothing needs you",
        EXIT_ATTENTION: "running, needs attention (open alert or missing key/grant)",
        EXIT_STOPPED: "not running",
    }.get(r.returncode, f"unexpected exit {r.returncode}")

    text = (r.stdout or "") + (r.stderr or "")

    # The data directory is mode 0700 and owned by the service account, so a
    # plain user gets a refusal rather than a status. Surface the fix the
    # binary itself prints instead of reporting "unexpected exit".
    if "only the service's account may read" in text or "Permission denied" in text:
        m = re.search(r"sudo -u (\S+)", text)
        user = m.group(1) if m else "<service user>"
        dd = re.search(r'"([^"]*6529-validator[^"]*)"', text)
        hint = f"sudo -u {user} validator status"
        if dd:
            hint += f' --data-dir "{dd.group(1)}"'
        return {
            "exit_code": r.returncode,
            "healthy": None,
            "needs_attention": False,
            "meaning": "cannot read the validator data directory from this account",
            "permission_denied": True,
            "run_as": user,
            "hint": hint,
            "alerts": None,
            "raw": text.strip()[:500],
        }

    payload: Any = None
    if as_json and r.stdout.strip():
        try:
            payload = json.loads(r.stdout)
        except json.JSONDecodeError:
            payload = None
    return {
        "exit_code": r.returncode,
        "healthy": r.returncode == EXIT_OK,
        # Unknown exit codes are an explicit attention state, not a healthy
        # state hidden behind the word "unexpected". The validator's status
        # contract is finite; fail closed when a newer binary adds a code.
        "needs_attention": r.returncode != EXIT_OK,
        "meaning": meaning,
        "alerts": (payload or {}).get("alerts") if isinstance(payload, dict) else None,
        "raw": payload if payload is not None else text[:4000],
    }


def grant_draft(account: str, key_code: str, data_dir: Optional[str] = None,
                binary: str = VALIDATOR_BIN) -> Dict[str, Any]:
    """Draft the grant as EIP-712 typed data.

    Requires the validator to be running (it supplies a recent finalized
    Ethereum block), or pass --ref-block yourself.
    """
    r = _run(["grant", "draft", "--account", account, "--key", key_code, "--json"],
             data_dir, binary)
    if r.returncode != 0:
        raise ValidatorError((r.stderr or r.stdout or "grant draft failed")[:500])
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise ValidatorError(f"grant draft returned non-JSON: {e}") from None


def grant_import(signature: str, data_dir: Optional[str] = None,
                 binary: str = VALIDATOR_BIN,
                 account: Optional[str] = None) -> str:
    """Hand the wallet's signature back to the validator."""
    args = ["grant", "import", "--signature", signature]
    if account:
        args += ["--account", account]
    r = _run(args, data_dir, binary)
    if r.returncode != 0:
        raise ValidatorError((r.stderr or r.stdout or "grant import failed")[:500])
    return (r.stdout or "").strip()


def pause(data_dir: Optional[str] = None, binary: str = VALIDATOR_BIN) -> str:
    return (_run(["pause"], data_dir, binary).stdout or "").strip()


def resume(data_dir: Optional[str] = None, binary: str = VALIDATOR_BIN) -> str:
    return (_run(["resume"], data_dir, binary).stdout or "").strip()
