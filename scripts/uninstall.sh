#!/usr/bin/env bash
#
# uninstall.sh — remove board-steward's runtime side-effects.
#
# Board-steward installs as a Claude Code plugin, but at runtime it also creates
# things the plugin system does NOT track and `/plugin uninstall` will NOT remove:
#   - the skill symlink in ${CLAUDE_CONFIG_DIR:-~/.claude}/skills/board-steward
#   - hooks wired into ${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json
#   - an autostart agent (launchd / systemd / Task Scheduler) running serve.py
#   - the live board HTTP server (on its port)
#   - the ~/.board-steward/ port registry  (only with --purge)
#
# This script cleans those up. It does NOT delete the plugin code itself or your
# board.json — run `/plugin uninstall board-steward@workboard` in Claude Code for
# the plugin files, and your board/ dir is project data you keep or delete yourself.
#
# Usage:
#   ./uninstall.sh                 # stop autostart + server, remove skill + hooks
#   ./uninstall.sh --port 7891     # be explicit about which server port to free
#   ./uninstall.sh --purge         # also remove ~/.board-steward/ port registry
#   ./uninstall.sh --dry-run       # show what would happen, change nothing
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=""
PURGE=0
DRY=0
DRY_FLAG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --port)    PORT="$2"; shift 2 ;;
    --purge)   PURGE=1; shift ;;
    --dry-run) DRY=1; DRY_FLAG="--dry-run"; shift ;;
    -h|--help) sed -n '2,35p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

run() { if [ "$DRY" = 1 ]; then echo "  DRY-RUN (would run): $*"; else eval "$*"; fi; }

# ---- dry-run: print the plan and exit without changing anything ---------------
if [ "$DRY" = 1 ]; then
  CFG_BASE="${CLAUDE_CONFIG_DIR:-${HOME}/.claude}"
  SKILL_LINK="${CFG_BASE}/skills/board-steward"
  PORT_LABEL="${PORT:-<auto-detect from port registry>}"
  echo
  echo "board-steward uninstall DRY-RUN — what a real run would remove (nothing below is changed):"
  echo
  echo "  1. skill symlink   → ${SKILL_LINK}"
  echo "                       (remove symlink / copied dir; plugin code in the repo is kept)"
  echo "  2. hooks           → ${CFG_BASE}/settings.json"
  echo "                       (remove all board-steward hook entries via install_hooks.py --uninstall)"
  echo "  3. autostart       → launchd agent / systemd unit / Task Scheduler task"
  echo "                       (remove login service via install_autostart.py --uninstall)"
  echo "  4. server          → kill process holding port ${PORT_LABEL}"
  echo "                       (free the board HTTP server; pass --port N to be explicit)"
  if [ "$PURGE" = 1 ]; then
    echo "  5. registry        → ${HOME}/.board-steward/"
    echo "                       (remove port-assignments + telemetry; --purge was passed)"
  else
    echo "  5. registry        → ${HOME}/.board-steward/ KEPT (pass --purge to also remove)"
  fi
  echo
  echo "  (plugin code + board/ data are never touched by this script)"
  echo
  echo "DRY-RUN complete — nothing was removed."
  exit 0
fi

echo "board-steward uninstall — removing runtime side-effects"
echo "  (plugin code + board.json are left alone; see header)"
echo ""

# 1. skill symlink / copied dir
CFG_BASE="${CLAUDE_CONFIG_DIR:-${HOME}/.claude}"
SKILL_LINK="${CFG_BASE}/skills/board-steward"
echo "1) removing skill symlink / dir at ${SKILL_LINK} …"
if [ -e "$SKILL_LINK" ] || [ -L "$SKILL_LINK" ]; then
  run "rm -rf \"${SKILL_LINK}\""
  echo "   removed"
else
  echo "   (not found — already absent)"
fi

# 2. hooks in settings.json
echo "2) removing board-steward hooks from settings.json…"
python3 "$SCRIPT_DIR/install_hooks.py" --uninstall || echo "   (no hooks to remove)"

# 3. autostart agent (launchd/systemd/taskscheduler) — also stops the KeepAlive server
echo "3) removing autostart agent…"
python3 "$SCRIPT_DIR/install_autostart.py" --uninstall || echo "   (autostart already absent)"

# 4. belt-and-suspenders: free the port if a stray server still holds it
if [ -n "$PORT" ]; then
  STRAY="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
  if [ -n "$STRAY" ]; then
    echo "4) freeing port $PORT (stray pid $STRAY)…"
    run "kill $STRAY 2>/dev/null || true"
  else
    echo "4) port $PORT already free"
  fi
else
  echo "4) no --port given; skipping stray-port check (pass --port N to kill a stray server)"
fi

# 5. optional: purge the port registry / state dir
if [ "$PURGE" = 1 ]; then
  echo "5) purging ~/.board-steward/ …"
  run "rm -rf \"$HOME/.board-steward\""
else
  echo "5) keeping ~/.board-steward/ (pass --purge to remove)"
fi

echo ""
echo "done — runtime side-effects removed."
echo "  To remove the plugin itself, in Claude Code run:"
echo "      /plugin uninstall board-steward@workboard"
echo "      /plugin marketplace remove workboard   # optional"
echo "  Your board/ dir (board.json + history) was left untouched."
