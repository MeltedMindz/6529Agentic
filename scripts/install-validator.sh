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
tar -xzf "$FILE"
DIR="${FILE%.tar.gz}"
if [ "$OS" = darwin ]; then ROOT=/usr/local/6529-validator; else ROOT=/opt/6529-validator; fi
sudo mkdir -p "$ROOT" /usr/local/bin
sudo cp -R "$DIR" "$ROOT/"
sudo ln -sfn "$ROOT/$DIR/validator" /usr/local/bin/validator
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
