#!/usr/bin/env bash
# install.sh - install the 6529 skills into an agent's skill directory.
#
#   ./skills/install.sh                 # auto-detect the host
#   ./skills/install.sh --to <dir>      # explicit
#   ./skills/install.sh --list          # what is available
#   ./skills/install.sh --check         # where it would install, no changes
#
# Skills are copied, not symlinked, so an agent keeps working if this
# checkout moves. Re-run to update.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"

SKILLS=()
while IFS= read -r d; do SKILLS+=("$(basename "$d")"); done \
  < <(find "$HERE" -mindepth 1 -maxdepth 1 -type d | sort)

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; }

if [ "${1:-}" = "--list" ]; then
  echo "Available skills:"
  for s in "${SKILLS[@]}"; do
    desc=$(awk -F': ' '/^description:/{print substr($0,14); exit}' "$HERE/$s/SKILL.md")
    printf "  %-20s %s\n" "$s" "${desc:0:88}"
  done
  exit 0
fi

TARGET=""
CHECK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --to) TARGET="${2:?--to needs a directory}"; shift 2 ;;
    --check) CHECK=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

# Auto-detect, most specific first. Add your host here if it is missing.
if [ -z "$TARGET" ]; then
  for c in "$HOME/.hermes/skills" \
           "$HOME/.claude/skills" \
           "$HOME/.config/agent/skills" \
           "$HOME/.openclaw/skills"; do
    [ -d "$c" ] && { TARGET="$c"; break; }
  done
fi
[ -z "$TARGET" ] && {
  echo "No skill directory found. Pass one with --to <dir>." >&2
  echo "Looked in: ~/.hermes/skills ~/.claude/skills ~/.config/agent/skills ~/.openclaw/skills" >&2
  exit 1; }

echo "repo    : $REPO"
echo "target  : $TARGET"
echo "skills  : ${#SKILLS[@]}"
[ "$CHECK" = 1 ] && { echo; echo "--check: nothing changed."; exit 0; }

mkdir -p "$TARGET"
for s in "${SKILLS[@]}"; do
  rm -rf "${TARGET:?}/$s"
  cp -R "$HERE/$s" "$TARGET/$s"
  # The skills call ./bin/6529, which only resolves from the repo. Record the
  # absolute path so an agent invoked from anywhere can still find it.
  printf '\n<!-- installed from %s on %s -->\n' "$REPO" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    >> "$TARGET/$s/SKILL.md"
  sed -i '' "s|\./bin/6529|$REPO/bin/6529|g" "$TARGET/$s/SKILL.md" 2>/dev/null \
    || sed -i "s|\./bin/6529|$REPO/bin/6529|g" "$TARGET/$s/SKILL.md"
  sed -i '' "s|\./scripts/install-validator\.sh|$REPO/scripts/install-validator.sh|g" \
    "$TARGET/$s/SKILL.md" 2>/dev/null \
    || sed -i "s|\./scripts/install-validator\.sh|$REPO/scripts/install-validator.sh|g" \
       "$TARGET/$s/SKILL.md"
  echo "  installed $s"
done

cat <<NEXT

Done. ${#SKILLS[@]} skills in $TARGET

Check your host picked them up, for example:
  hermes skills list | grep 6529

If your agent has not been onboarded yet, start with the 6529-onboarding skill
or read AGENT.md in this repo.
NEXT
