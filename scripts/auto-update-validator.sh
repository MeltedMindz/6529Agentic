#!/usr/bin/env bash
# auto-update-validator.sh - keep a validator on the current release, safely.
#
# For the install shape that does NOT update itself. From rc.14 the validator
# installs its own updates on Windows, in the Mac app and from the Linux .deb
# - but a tarball install under /usr/local, run as a system service, is not
# any of those and will sit on an old release forever. This closes that.
#
#   ./scripts/auto-update-validator.sh --check   # report only, change nothing
#   ./scripts/auto-update-validator.sh           # update if there is one
#
# What it will not do:
#   * install a build whose SHA-256 does not match the signed feed
#     (install-validator.sh refuses, and this stops there)
#   * touch anything while today's vote is still due - signing comes first
#   * leave you on a broken release: if the new binary will not run or the
#     service will not come back, the previous build is restored
#
# Needs root to install. In cron there is no terminal, so set SUDO_ASKPASS to
# a helper that prints the password, or give the cron user a NOPASSWD rule.
#
# Exit codes: 0 nothing to do, or updated and verified
#             4 deferred (a vote is due) - try again later
#             5 needs a human: update failed, or rolled back
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
BIN="${VALIDATOR_BIN:-/usr/local/bin/validator}"
FEED="${AGENT6529_VALIDATOR_FEED:-https://6529.io/validator/releases.json}"
SERVICE="${VALIDATOR_SERVICE:-system/io.6529.validator}"
DATA_DIR="${VALIDATOR_DATA_DIR:-/Library/Application Support/6529-validator}"
SVC_USER="${VALIDATOR_USER:-_validator6529}"
PY="${PYTHON:-python3}"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

say()  { printf '%s\n' "$*"; }
fail() { printf 'validator auto-update: %s\n' "$*" >&2; }

SUDO=(sudo)
[ -n "${SUDO_ASKPASS:-}" ] && SUDO=(sudo -A)
root() { "${SUDO[@]}" "$@"; }

# ---------------------------------------------------------------- what we have
installed="$("$BIN" --version 2>/dev/null | awk '{print $2}')"
[ -n "$installed" ] || { fail "no validator at $BIN"; exit 5; }

latest="$(curl -fsSL --max-time 60 "$FEED" 2>/dev/null \
  | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["releases"][0]["version"])' 2>/dev/null)"
[ -n "$latest" ] || { fail "cannot read the release feed"; exit 0; }

if [ "$installed" = "$latest" ]; then
  [ "$CHECK_ONLY" = 1 ] && say "validator $installed is current"
  exit 0
fi

say "validator update available: $installed -> $latest"
if [ "$CHECK_ONLY" = 1 ]; then
  say "--check: nothing changed."
  exit 0
fi

# -------------------------------------------------- signing comes before updating
# Reading the ledger needs the service account. If that cannot be checked, do
# not guess: an unknown signing state is a reason to wait, not to proceed.
status="$(root -u "$SVC_USER" "$BIN" status --data-dir "$DATA_DIR" 2>&1)" || status=""
if [ -z "$status" ]; then
  fail "cannot read validator status as $SVC_USER; deferring rather than updating blind"
  exit 4
fi
if ! printf '%s' "$status" | grep -qiE "signature is sent|nothing to do"; then
  say "today's vote is not sent yet; deferring the update"
  exit 4
fi

PREV="$(readlink "$BIN" 2>/dev/null || true)"
[ -n "$PREV" ] || fail "warning: $BIN is not a symlink, rollback will not be automatic"

# ---------------------------------------------------------------------- install
if ! "$HERE/install-validator.sh" >/tmp/validator-update.$$.log 2>&1; then
  fail "install failed, nothing was switched. Last lines:"
  tail -5 /tmp/validator-update.$$.log >&2
  rm -f /tmp/validator-update.$$.log
  exit 5
fi
rm -f /tmp/validator-update.$$.log

restore() {
  [ -n "$PREV" ] || { fail "no previous build recorded; cannot roll back"; return 1; }
  fail "rolling back to ${PREV%/validator}"
  root ln -sfn "$PREV" "$BIN"
  root launchctl kickstart -k "$SERVICE" >/dev/null 2>&1
  sleep 5
}

# ----------------------------------------------------------------- verify + roll
now="$("$BIN" --version 2>/dev/null | awk '{print $2}')"
if [ "$now" != "$latest" ]; then
  fail "after install the binary reports '${now:-nothing}', expected $latest"
  restore
  exit 5
fi

root launchctl kickstart -k "$SERVICE" >/dev/null 2>&1
for _ in 1 2 3 4 5 6 7 8 9 10; do
  sleep 3
  pid="$(root launchctl print "$SERVICE" 2>/dev/null | awk '/^[[:space:]]*pid =/{print $3; exit}')"
  [ -n "${pid:-}" ] && break
done
if [ -z "${pid:-}" ]; then
  fail "service did not come back on $latest"
  restore
  exit 5
fi

after="$(root -u "$SVC_USER" "$BIN" status --data-dir "$DATA_DIR" 2>&1)" || after=""
if [ -z "$after" ]; then
  fail "service is running on $latest but its status is unreadable"
  restore
  exit 5
fi

say "updated $installed -> $latest, service running (pid $pid), status readable"
printf '%s\n' "$after" | sed -n '1,8p' | sed 's/^/  /'
say "previous build kept at ${PREV%/validator}"
exit 0
