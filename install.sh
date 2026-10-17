#!/usr/bin/env bash
# Install the run-in-session skill for Claude Code.
#   ./install.sh
# Shared layout (same as WayOfWork): ~/.agents/skills/run-in-session points at this repo, and
# ~/.claude/skills/run-in-session points at ../../.agents/skills/run-in-session. Only Claude Code: the skill relies on
# its ListAgents and SendMessage tools. Re-running is safe. A real directory with the skill's name is never replaced:
# the script stops with exit 1.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="run-in-session"
case "${1:-}" in
  -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
  "") ;;
  *) echo "unknown argument: $1" >&2; exit 2 ;;
esac

link() {  # link <target> <path>: create or refresh a symlink, never replace a real file or directory
  if [ -e "$2" ] && [ ! -L "$2" ]; then
    echo "refusing to replace $2: it is not a symlink; move it away and re-run" >&2
    return 1
  fi
  mkdir -p "$(dirname "$2")"
  ln -sfn "$1" "$2"
}

status=0
link "$REPO" "$HOME/.agents/skills/$NAME" || exit 1
link "../../.agents/skills/$NAME" "$HOME/.claude/skills/$NAME" || status=1
command -v python3 >/dev/null || { echo "note: python3 is not on PATH; ris needs it" >&2; status=1; }
echo "skill: $NAME -> $REPO"
exit "$status"
