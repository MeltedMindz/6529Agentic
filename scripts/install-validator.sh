#!/usr/bin/env bash
# install-validator.sh - download, VERIFY and install the 6529 validator.
#
# Reads the signed release feed for the current version, downloads the build
# for this machine, checks its SHA-256 against both SHA256SUMS and the feed,
# and only then installs. An unverified build is never installed.
#
# It stops before `service install` so you see what will change first.
#
#   ./scripts/install-validator.sh            # install the current release
#   ./scripts/install-validator.sh --check    # report only, change nothing
set -euo pipefail

FEED="${AGENT6529_VALIDATOR_FEED:-https://6529.io/validator/releases.json}"
DOWNLOAD="${AGENT6529_VALIDATOR_DOWNLOAD:-https://6529.io/validator/download}"
PY="${PYTHON:-python3}"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

say() { printf '\n== %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# Installing needs root. On a headless box - the case this is written for -
# there is no terminal for sudo to prompt on, so honour SUDO_ASKPASS when it
# is set and fail with the fix rather than "a terminal is required".
SUDO=(sudo)
if [ -n "${SUDO_ASKPASS:-}" ]; then
  [ -x "$SUDO_ASKPASS" ] || die "SUDO_ASKPASS is set but not executable: $SUDO_ASKPASS"
  SUDO=(sudo -A)
fi
need_root() {
  "${SUDO[@]}" -n true 2>/dev/null && return 0
  "${SUDO[@]}" true 2>/dev/null && return 0
  die "cannot get root. Run 'sudo -v' first, or set SUDO_ASKPASS to a helper
       that prints the password (see docs/VALIDATOR.md)."
}

case "$(uname -s)" in
  Darwin) OS=darwin ;;
  Linux)  OS=linux  ;;
  *) die "unsupported OS: $(uname -s)" ;;
esac
case "$(uname -m)" in
  arm64|aarch64) ARCH=aarch64 ;;
  x86_64|amd64)  ARCH=x86_64  ;;
  *) die "unsupported arch: $(uname -m)" ;;
esac
if [ "$OS" = darwin ]; then TARGET="$ARCH-apple-darwin"; else TARGET="$ARCH-unknown-linux-gnu"; fi

say "Reading the signed release feed"
META="$(curl -fsSL --max-time 60 "$FEED")" || die "cannot reach $FEED"
read -r REL MINSUP DEADLINE <<<"$("$PY" -c '
import json,sys
d=json.load(sys.stdin)
print(d["releases"][0]["version"], d.get("min_supported","?"), d.get("deadline","-"))
' <<<"$META")"
FILE="$("$PY" -c '
import json,sys
d=json.load(sys.stdin); t=sys.argv[1]
ext=".zip" if "windows" in t else ".tar.gz"
print(next(f["name"] for f in d["releases"][0]["files"]
           if t in f["name"] and f["name"].endswith(ext)))
' "$TARGET" <<<"$META")"
WANT="$("$PY" -c '
import json,sys
d=json.load(sys.stdin); n=sys.argv[1]
print(next(f["sha256"] for f in d["releases"][0]["files"] if f["name"]==n))
' "$FILE" <<<"$META")"

printf '  machine        %s\n  release        %s\n  min_supported  %s\n  deadline       %s\n  artifact       %s\n' \
  "$TARGET" "$REL" "$MINSUP" "$DEADLINE" "$FILE"

if command -v validator >/dev/null 2>&1; then
  printf '  installed      %s\n' "$(validator --version 2>/dev/null | awk '{print $2}')"
else
  printf '  installed      (none)\n'
fi
[ "$CHECK_ONLY" = 1 ] && { echo; echo "--check: nothing changed."; exit 0; }

WORK="${TMPDIR:-/tmp}/6529-validator-$REL"
mkdir -p "$WORK" && cd "$WORK"

say "Downloading"
curl -fL --progress-bar -o "$FILE" "$DOWNLOAD/$REL/$FILE"
curl -fsSL -o SHA256SUMS "$DOWNLOAD/$REL/SHA256SUMS"

say "Verifying"
if command -v sha256sum >/dev/null 2>&1; then
  grep " $FILE\$" SHA256SUMS | sha256sum -c - || die "SHA256SUMS check FAILED - do not run this build"
  GOT="$(sha256sum "$FILE" | cut -d' ' -f1)"
else
  grep " $FILE\$" SHA256SUMS | shasum -a 256 -c - || die "SHA256SUMS check FAILED - do not run this build"
  GOT="$(shasum -a 256 "$FILE" | cut -d' ' -f1)"
fi
[ "$GOT" = "$WANT" ] || die "digest does not match the signed feed: $GOT != $WANT"
printf '  SHA256SUMS ok, and matches the signed feed\n'

say "Installing"
need_root
tar -xzf "$FILE"
DIR="${FILE%.tar.gz}"
if [ "$OS" = darwin ]; then ROOT=/usr/local/6529-validator; else ROOT=/opt/6529-validator; fi
"${SUDO[@]}" mkdir -p "$ROOT" /usr/local/bin

# Every release candidate ships as version "0.1.0", so the tarball's own
# directory name is identical for rc.12 and rc.13. Installing it verbatim
# overwrites the running version and destroys the rollback - which is exactly
# what happened to us. Qualify the directory with the release instead, so
# versions sit side by side and rolling back is a symlink change.
DEST="$ROOT/validator-$REL-$TARGET"
[ -n "$REL" ] || die "no release version to install under"
"${SUDO[@]}" rm -rf -- "$DEST.incoming"
"${SUDO[@]}" cp -R "$DIR" "$DEST.incoming"
if [ -e "$DEST" ]; then
  printf '  %s is already installed; replacing it\n' "$REL"
  "${SUDO[@]}" rm -rf -- "$DEST"
fi
"${SUDO[@]}" mv -- "$DEST.incoming" "$DEST"
PREV="$(readlink /usr/local/bin/validator 2>/dev/null || true)"
"${SUDO[@]}" ln -sfn "$DEST/validator" /usr/local/bin/validator
if [ -n "$PREV" ] && [ "$PREV" != "$DEST/validator" ]; then
  printf '  previous build kept at %s\n' "${PREV%/validator}"
  printf '  roll back with: sudo ln -sfn %s /usr/local/bin/validator\n' "$PREV"
fi
validator --version

cat <<NEXT

Installed. The service is NOT running yet - review each step before it changes
anything:

  sudo validator service install --dry-run    # see exactly what would change
  sudo validator service install
NEXT
if [ "$OS" = darwin ]; then
  DD="/Library/Application Support/6529-validator"; USER_=_validator6529
else
  DD="/var/lib/6529-validator"; USER_=validator6529
fi
cat <<NEXT
  sudo -u $USER_ validator init   --data-dir "$DD"
  sudo -u $USER_ validator keygen --data-dir "$DD" --label "this machine"
  sudo validator service install              # again: now it starts

Then authorize the key with a wallet of the account whose TDH you are
attesting (docs/VALIDATOR.md). Until a grant exists it runs as a Watcher: it
validates, but signs nothing.

  ./bin/6529 validator watch                  # health + release currency
NEXT
