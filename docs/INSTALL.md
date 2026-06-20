# WorkBoard / board-steward — Install Reference

This document describes the exact on-disk footprint of a WorkBoard install and
the per-component runtime behaviour.  Every claim here was verified against the
source files listed in parentheses.  Nothing is guessed or copied from marketing
text.

To see what a real install would do WITHOUT writing anything:

```
./install.sh --dry-run
```

To undo the install side-effects:

```
bash scripts/uninstall.sh --dry-run   # preview
bash scripts/uninstall.sh             # execute
```

---

## One-command install

```
./install.sh                      # install to $(pwd)
./install.sh --project ~/code/foo # install to a specific project
./install.sh --autostart          # also register a login service (opt-in)
./install.sh --dry-run            # print the plan, write nothing
```

The installer (`install.sh`) runs five steps in order (source: `install.sh`):

1. Install the skill (symlink).
2. Bootstrap a board (`serve.py --bootstrap`) and start the server.
3. Wire Claude Code hooks (`install_hooks.py --hook all`).
4. Register a login service — **opt-in only** (`--autostart`; off by default).
5. Open the board in the browser.

---

## What changes on disk

### 1. Skill symlink

Path (source: `install.sh`, step 1):

```
${CLAUDE_CONFIG_DIR:-~/.claude}/skills/board-steward
```

This is a symlink pointing at the repo root.  On Windows (Git Bash) where
symlinks require elevated permissions, `install.sh` falls back to a plain
directory copy to the same path.

### 2. Claude Code hooks in settings.json

Path (source: `scripts/install_hooks.py`, function `claude_settings_path`):

```
${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json
```

`install_hooks.py --hook all` wires the following hook events (source:
`hooks/hooks.json` and `scripts/install_hooks.py`, `HOOK_VARIANTS` dict and the
`"live"/"all"` branch in `main()`):

| Event | Script | What it does |
|---|---|---|
| `SessionStart` | `hook_session_start.sh` | Fires once per session. Injects a compact board digest (~222 tokens per `docs/TOKEN_BUDGET.md`) so Claude knows the current board shape without loading `board.json`. |
| `UserPromptSubmit` | `hook_user_prompt.sh` | **Fires on every user prompt.** Injects a board-protocol reminder into context before Claude responds. This is the per-turn token cost (source: `docs/TOKEN_BUDGET.md`): **~309 tokens per prompt** (approximately 355 Claude tokens). Over a 50-turn session that is ~15,450 tokens — the dominant interactive overhead. The hook also auto-spawns the server if no live server is found on the board's designated port. |
| `PreToolUse` (matcher: `Edit|Write|MultiEdit|NotebookEdit`) | `hook_pre_tool_use.sh` | Fires before any file-mutating tool. Checks the LIVE protocol flash and auto-links the edited file to the active card (#102). |
| `PreToolUse` (matcher: `Edit|Write|MultiEdit|NotebookEdit`) | `hook_card_before_edit.sh` | Fires before any file-mutating tool. Emits a non-blocking warning if no card is declared for the current edit (#75). |
| `Stop` | `hook_stop.sh` | Fires when the agent finishes a turn (sign-off). Checks whether the turn's work was carded and whether anything is still In-Progress; can block the stop to force carding (#279/#359/#592). |

The `SubagentStop` event appears in `hooks/hooks.json` but is **not** in
`HOOK_VARIANTS` and is therefore **not wired by `install_hooks.py`**.  The
`hook_subagent_stop.sh` script exists on disk but is not registered
automatically.

`install_hooks.py` backs up `settings.json` (timestamped `.bak-<UTC>`) before
any write.  All mutations are atomic (write-to-tmp then `replace`).  The
operation is idempotent: re-running is safe.

### 3. Project board directory

Created by `serve.py --bootstrap` inside the target project:

```
<project>/board/board.json      # card data
<project>/board/board.html      # board UI (served from skill template, not copied)
<project>/.board-server.log     # server stdout/stderr
<project>/board/.board-server.pid  # PID file (created by port registry)
```

`board.json` is the only persistent project-level data.  `board.html` is always
served from the skill's `templates/` directory (source: `scripts/serve.py`,
`TEMPLATE_HTML`); per-project copies are not created.

### 4. Port registry (`~/.board-steward/`)

The port registry maps each project's `board/` directory to its designated port
and running PID (source: `scripts/serve.py`, `port_registry` import;
`scripts/install_hooks.py` reads `~/.board-steward/` for telemetry):

```
~/.board-steward/port-assignments.json   # board-dir → port mapping (sticky)
~/.board-steward/port-registry.json      # board-dir → {port, pid} at runtime
~/.board-steward/telemetry/events.jsonl  # card-event log (hook telemetry)
```

Pass `--purge` to `uninstall.sh` to remove this directory.

---

## Server — port and transport

Source: `scripts/serve.py`.

- Binds `127.0.0.1:<port>` by default (loopback only, no auth required).
- Default port **7891**; each project gets a **sticky designation** via the
  port registry so a second project on the same machine is assigned a different
  port automatically.
- Pure Python stdlib — no pip dependencies.
- Live board state is pushed to the browser via Server-Sent Events (`GET /events`).
- A `GET /health` endpoint reports liveness, card count, rev, and SSE client count.

---

## Background service (autostart) — opt-in

Source: `install.sh` (default `DO_AUTOSTART=0`), `scripts/install_autostart.py`.

Autostart is **off by default**.  Pass `--autostart` to `install.sh` to
register a login service that starts `serve.py` automatically at login.

`install_autostart.py` dispatches to the correct platform installer:

| Platform | Mechanism |
|---|---|
| macOS (`darwin`) | `install_launchd.py` — registers a launchd user agent |
| Linux | `install_systemd.py` — registers a `systemd --user` service |
| Windows (`win32`) | `install_taskscheduler.py` — creates a Task Scheduler ONLOGON task |

Without `--autostart` the server is either started manually (`python scripts/serve.py`)
or auto-spawned on demand by the `UserPromptSubmit` hook the first time Claude
opens a prompt in a project that has a board (source: `scripts/hook_user_prompt.sh`,
auto-spawn block).

---

## Uninstall

`scripts/uninstall.sh` removes the runtime side-effects (autostart service,
stray server process, legacy settings-based hooks, and optionally the port
registry).  It does NOT delete plugin code or your `board/` directory.

Preview what would be removed:

```
bash scripts/uninstall.sh --dry-run
```

Execute the uninstall:

```
bash scripts/uninstall.sh           # remove autostart + legacy hooks
bash scripts/uninstall.sh --port 7891  # also free a stray server on that port
bash scripts/uninstall.sh --purge   # also remove ~/.board-steward/
```

To remove the plugin skill itself, run inside Claude Code:

```
/plugin uninstall board-steward@workboard
```

---

## Per-turn token cost — summary

Source: `docs/TOKEN_BUDGET.md` (measured 2026-05-28, re-measured 2026-06-10).

| Component | Tokens | Frequency |
|---|---|---|
| SessionStart digest | ~222 | Once per session |
| UserPromptSubmit protocol nudge | ~309 (~355 Claude) | Every prompt |
| SKILL.md body (when board is engaged) | ~4,065 | Per board-engagement session |
| board.json | never auto-loaded | On explicit Read only |

The per-prompt UserPromptSubmit injection is the dominant interactive overhead.
At 50 turns it totals ~15,450 tokens.  See `docs/TOKEN_BUDGET.md` for the full
session cost model and trimming options.
