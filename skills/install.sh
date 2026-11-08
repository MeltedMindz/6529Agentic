#!/usr/bin/env bash
# install.sh - install the 6529 skills into an agent's skill directory.
#
#   ./skills/install.sh                 # auto-detect the host
#   ./skills/install.sh --to <dir>      # explicit
#   ./skills/install.sh --list          # what is available
#   ./skills/install.sh --check         # what would change, no changes
#   ./skills/install.sh --force         # overwrite local edits (keeps a backup)
#
# Local edits are preserved. An agent that learns something and writes it into
# its own installed skill should not lose that on the next update, so:
#
#   * a SKILL.md that differs from what was installed is treated as modified.
#     It is backed up to SKILL.md.local-<timestamp> and NOT overwritten unless
#     you pass --force.
#   * LOCAL.md inside an installed skill is never touched. That is the durable
#     place for an agent's own notes, and hosts load it alongside SKILL.md.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

SKILLS=()
while IFS= read -r d; do SKILLS+=("$(basename "$d")"); done \
  < <(find "$HERE" -mindepth 1 -maxdepth 1 -type d | sort)

sha() { shasum -a 256 "$1" 2>/dev/null | cut -d' ' -f1 || sha256sum "$1" | cut -d' ' -f1; }
usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; }

if [ "${1:-}" = "--list" ]; then
  echo "Available skills:"
  for s in "${SKILLS[@]}"; do
    desc=$(awk -F': ' '/^description:/{print substr($0,14); exit}' "$HERE/$s/SKILL.md")
    printf "  %-20s %s\n" "$s" "${desc:0:88}"
  done
  exit 0
fi

TARGET=""; CHECK=0; FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --to) TARGET="${2:?--to needs a directory}"; shift 2 ;;
    --check) CHECK=1; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [ -z "$TARGET" ]; then
  for c in "$HOME/.hermes/skills" "$HOME/.claude/skills" \
           "$HOME/.config/agent/skills" "$HOME/.openclaw/skills"; do
    [ -d "$c" ] && { TARGET="$c"; break; }
  done
fi
[ -z "$TARGET" ] && {
  echo "No skill directory found. Pass one with --to <dir>." >&2; exit 1; }

echo "repo    : $REPO"
echo "target  : $TARGET"
echo "skills  : ${#SKILLS[@]}"
echo

install_one() {
  local s="$1" dst="$TARGET/$s" src="$HERE/$s/SKILL.md"
  local stamp="$dst/.installed-sha" preserved=""

  if [ -f "$dst/SKILL.md" ] && [ -f "$stamp" ]; then
    if [ "$(sha "$dst/SKILL.md")" != "$(cat "$stamp")" ]; then
      if [ "$FORCE" = 0 ]; then
        echo "  SKIPPED  $s - locally modified. Keeping your version."
        echo "           --force to replace it (a backup is kept either way)."
        return 0
      fi
      preserved="$dst/SKILL.md.local-$TS"
    fi
  fi

  mkdir -p "$dst"
  [ -n "$preserved" ] && cp "$dst/SKILL.md" "$preserved"
  # LOCAL.md and any .local-* backups survive: copy the source file only.
  cp "$src" "$dst/SKILL.md"
  for extra in "$HERE/$s"/*; do
    [ "$(basename "$extra")" = "SKILL.md" ] && continue
    [ -e "$extra" ] && cp -R "$extra" "$dst/" 2>/dev/null || true
  done

  # Skills call ./bin/6529, which only resolves from the repo. Record the
  # absolute path so an agent invoked from anywhere still finds it.
  for pat in "s|\./bin/6529|$REPO/bin/6529|g" \
             "s|\./scripts/install-validator\.sh|$REPO/scripts/install-validator.sh|g"; do
    sed -i '' "$pat" "$dst/SKILL.md" 2>/dev/null || sed -i "$pat" "$dst/SKILL.md"
  done
  printf '\n<!-- installed from %s on %s. Your own notes go in LOCAL.md, which\n     updates never touch. Edits to this file are preserved but will be\n     reported as modified on the next install. -->\n' \
    "$REPO" "$TS" >> "$dst/SKILL.md"
  sha "$dst/SKILL.md" > "$stamp"

  if [ -n "$preserved" ]; then
    echo "  updated  $s  (your version saved as $(basename "$preserved"))"
  else
    echo "  updated  $s"
  fi
}

if [ "$CHECK" = 1 ]; then
  for s in "${SKILLS[@]}"; do
    dst="$TARGET/$s"
    if [ ! -d "$dst" ]; then echo "  new       $s"
    elif [ -f "$dst/.installed-sha" ] && \
         [ "$(sha "$dst/SKILL.md")" != "$(cat "$dst/.installed-sha")" ]; then
      echo "  MODIFIED  $s - would be kept, not overwritten"
    else echo "  update    $s"; fi
    [ -f "$dst/LOCAL.md" ] && echo "            (LOCAL.md present, never touched)"
  done
  echo; echo "--check: nothing changed."; exit 0
fi

mkdir -p "$TARGET"
for s in "${SKILLS[@]}"; do install_one "$s"; done

cat <<NEXT

Done. ${#SKILLS[@]} skills in $TARGET

Your own notes: create LOCAL.md inside any installed skill. Updates never
touch it, so what an agent learns there survives.

Check your host picked them up, for example:
  hermes skills list | grep 6529
NEXT
