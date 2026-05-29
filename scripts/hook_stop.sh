#!/usr/bin/env bash
# board-steward Stop hook for #279 STOP-RECON-HOOK.
#
# Fires when the agent finishes responding (session sign-off). Reads the Stop
# JSON from stdin, hands it to the recon helper which checks whether this
# session's work got carded + whether anything is still In-Progress, and (only
# if there's a gap) writes board/recon_pending.json for the NEXT session to
# surface. The live "never-miss on sign-off" backstop.
#
# Must be SILENT and never block. Exits 0 always; hard timeout 5s.

set +e
set -u

PYHELPER="$(dirname "$0")/_hook_stop_recon.py"
if [ ! -f "${PYHELPER}" ]; then
  exit 0
fi

# Capture the Stop payload from stdin BEFORE backgrounding — a backgrounded
# process's stdin is detached from the pipe, and the helper needs the payload's
# transcript_path/cwd. Feed it back in via a pipe.
PAYLOAD="$(cat)"

# 5s hard timeout (a large session transcript takes a moment to scan); macOS has
# no `timeout`, so background + kill-on-overrun. Session-end, so no user latency.
(
  printf '%s' "${PAYLOAD}" | python3 "${PYHELPER}" &
  pid=$!
  ( sleep 5 ; kill -9 "${pid}" 2>/dev/null ) &
  watcher=$!
  wait "${pid}" 2>/dev/null
  kill -9 "${watcher}" 2>/dev/null
) >/dev/null 2>&1

exit 0
