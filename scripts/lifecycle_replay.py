#!/usr/bin/env python3
"""lifecycle_replay.py — turn-paced board replay.

Walks ~/.claude/projects/<proj>/*.jsonl in chronological order. Each turn
becomes a board action:
  - user_prompt (substantive)  → card.py add (col=task)
  - asst with Edit/Write       → fly active to inprogress (first time)
  - asst with clean ship hit   → fly active to done
  - asst with bug language     → fly active to inprogress --bug
  - git_commit                 → fly active to done (if not already)

Pacing:
  --turns-per-sec N  (default 2.0)  — fixed cadence per turn
  --gap-speedup N    (optional)     — preserve real idle gaps × speedup
                                       (overrides --turns-per-sec when set)

State: {active_card_num: int, active_column: str, last_substantive_prompt_ts}.
Trivial prompts (yes/ok/sure / [Request interrupted]) attach as follow-ups
to the active card — no new card opened.

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Reuse harvesters + classifiers from discover2 and title rewriter from sim_titler.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from discover2 import (
    harvest_jsonl, harvest_convo, harvest_git, harvest_memory, harvest_plans,
    parse_ts, is_trivial, classify_ship, MANDATORY_RE, BUG_RE,
    SHIP_STRONG_RE, files_from_tool_use, msg_text,
)
from sim_titler import rewrite as titler_rewrite, prewarm_cache


def _flatten_events(project: Path, days: int) -> list[dict]:
    """Harvest all sources and merge into one chronological event list."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)
             if days > 0 else None)
    events: list[dict] = []
    events.extend(harvest_jsonl(since))
    events.extend(harvest_convo(since))
    events.extend(harvest_git(project, since))
    events.extend(harvest_memory(since))
    events.extend(harvest_plans(since))

    # Dedupe convo turns vs jsonl turns by (rounded text, kind family).
    seen_user: set[str] = set()
    seen_asst: set[str] = set()
    deduped: list[dict] = []
    for e in sorted(events, key=lambda x: x["ts"]):
        if e["kind"] in ("user_prompt", "convo_user"):
            head = (e["text"] or "").strip()[:80].lower()
            if head in seen_user:
                continue
            seen_user.add(head)
        elif e["kind"] in ("asst_msg", "convo_asst"):
            head = (e["text"] or "").strip()[:80].lower()
            if head and head in seen_asst:
                continue
            if head:
                seen_asst.add(head)
        deduped.append(e)
    return deduped


def _cwd_in_project(event: dict, project: Path) -> bool:
    cwd = (event.get("meta") or {}).get("cwd") or ""
    if not cwd:
        return False
    try:
        cp = Path(cwd).resolve()
        pp = project.resolve()
        return cp == pp or pp in cp.parents or cp in pp.parents
    except OSError:
        return False


def _card_add(card_py: Path, board: Path, prompt_text: str,
              asst_context: str, urgency: list[str],
              origin_prefix: str, use_llm: bool) -> int | None:
    """Run card.py add. Routes the prompt through sim_titler.rewrite to get a
    work-summary title, optional code, and notes — instead of plopping the
    first 80 chars of the raw prompt. Returns assigned num."""
    board_dir = board.parent
    rw = titler_rewrite(prompt_text, asst_context, board_dir=board_dir,
                        use_llm=use_llm)
    title = rw["title"] or prompt_text.strip()[:80]
    code = rw.get("code") or ""
    notes = rw.get("notes") or ""
    if code:
        title = f"{code}: {title}" if not title.lower().startswith(code.lower()) else title
    title = title[:80]

    col = "mandatory" if urgency else "task"
    origin = f"{origin_prefix} User: \"{prompt_text[:240]}\""
    args = [sys.executable, str(card_py), "--board", str(board), "add",
            "--column", col, "--priority", "mid",
            "--title", title, "--origin", origin[:400],
            "--tag", "discovered"]
    if notes:
        args += ["--notes", notes]
    if urgency:
        args += ["--tag", "mandatory"]
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=8)
    except subprocess.SubprocessError:
        return None
    if out.returncode != 0:
        return None
    m = re.search(r"#(\d+)", out.stdout)
    return int(m.group(1)) if m else None


def _card_fly(card_py: Path, board: Path, num: int, col: str,
              flags: dict[str, str] | None = None) -> bool:
    args = [sys.executable, str(card_py), "--board", str(board), "fly",
            str(num), col, "--pause-ms", "150"]
    for k, v in (flags or {}).items():
        args += [f"--{k}", v]
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=8)
    except subprocess.SubprocessError:
        return False
    return out.returncode == 0


def _card_subtask(card_py: Path, board: Path, num: int, text: str) -> bool:
    args = [sys.executable, str(card_py), "--board", str(board),
            "subtask", "add", str(num), text[:100]]
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=8)
    except subprocess.SubprocessError:
        return False
    return out.returncode == 0


def replay(project: Path, board: Path, port: int, days: int,
           turns_per_sec: float, gap_speedup: float | None,
           max_turns: int, use_llm: bool = True) -> None:
    events = _flatten_events(project, days)
    if not events:
        print("no events to replay", file=sys.stderr)
        return

    card_py = Path(__file__).resolve().parent / "card.py"
    if not card_py.exists():
        print(f"card.py not found at {card_py}", file=sys.stderr)
        return

    # Pre-warm the title cache BEFORE the replay starts so every card_add is
    # a cache hit (no inline LLM stutter).
    board_dir = board.parent
    def _progress(done: int, total: int) -> None:
        sys.stderr.write(f"\r▶ rewriting titles {done}/{total}…")
        sys.stderr.flush()
    print(f"▶ pre-warming title cache for {len(events)} events…",
          file=sys.stderr)
    counters = prewarm_cache(events, board_dir, workers=4,
                             use_llm=use_llm, progress_cb=_progress)
    sys.stderr.write("\n")
    print(f"  titled {counters['total']} unique prompts "
          f"(llm={counters['llm_called']}, "
          f"heuristic={counters['heuristic_only']}, "
          f"cached={counters['cached_hit']})",
          file=sys.stderr)

    print(f"▶ replaying {len(events)} events at "
          f"{'gap×' + str(gap_speedup) if gap_speedup else f'{turns_per_sec}/sec'}",
          file=sys.stderr)

    state: dict = {
        "active_num": None,
        "active_col": None,
        "active_has_files": False,
        "active_has_shipped": False,
        "prev_ts": None,
    }

    n_replayed = 0
    for ev in events:
        if max_turns and n_replayed >= max_turns:
            break

        # ----- pacing -----
        if state["prev_ts"] is None:
            delay = 0.0
        elif gap_speedup is not None and gap_speedup > 0:
            real_gap = max(0.0, (ev["ts"] - state["prev_ts"]).total_seconds())
            delay = real_gap / gap_speedup
            delay = min(delay, 5.0)              # cap idle gaps at 5s wall
        else:
            delay = 1.0 / max(0.1, turns_per_sec)
        if delay > 0:
            time.sleep(delay)
        state["prev_ts"] = ev["ts"]

        # ----- dispatch -----
        kind = ev["kind"]

        if kind in ("user_prompt", "convo_user"):
            text = (ev["text"] or "").strip()
            if not text:
                continue
            if is_trivial(text):
                # Attach to active card if any
                if state["active_num"] is not None:
                    _card_subtask(card_py, board, state["active_num"],
                                  text[:80])
                continue
            # Project-scope filter: skip jsonl prompts from unrelated cwds.
            # Convo lines and prompts without cwd info pass through.
            if kind == "user_prompt" and ev.get("meta", {}).get("cwd"):
                if not _cwd_in_project(ev, project):
                    continue

            urgency = [m.group(0).lower()
                       for m in [MANDATORY_RE.search(text)] if m]
            # Grab the immediate next asst_msg text for LLM context (if any).
            ev_idx = events.index(ev) if ev in events else -1
            asst_ctx = ""
            for nx in events[ev_idx + 1: ev_idx + 5]:
                if nx["kind"] in ("asst_msg", "convo_asst") and nx.get("text"):
                    asst_ctx = nx["text"][:1200]
                    break
            origin_prefix = f"Sim replay (turn {n_replayed+1})."
            num = _card_add(card_py, board, text, asst_ctx, urgency,
                            origin_prefix, use_llm)
            if num is not None:
                state["active_num"] = num
                state["active_col"] = "mandatory" if urgency else "task"
                state["active_has_files"] = False
                state["active_has_shipped"] = False
                n_replayed += 1
            continue

        if kind in ("asst_msg", "convo_asst"):
            if state["active_num"] is None:
                continue
            text = ev["text"] or ""
            files = ev.get("files") or []
            head = text.strip().split("\n", 1)[0][:200]

            # First file edit → fly to inprogress (unless already past it)
            if files and not state["active_has_files"]:
                if state["active_col"] in ("task", "mandatory"):
                    if _card_fly(card_py, board, state["active_num"],
                                 "inprogress"):
                        state["active_col"] = "inprogress"
                state["active_has_files"] = True
                # also log the file as a subtask hint for visibility
                if files:
                    _card_subtask(card_py, board, state["active_num"],
                                  f"edit {Path(files[0]).name}")

            # Bug language after a prior ship → fly back ip with --bug
            if (state["active_has_shipped"]
                    and BUG_RE.search(head)
                    and not SHIP_STRONG_RE.search(head)):
                reason = head[:60]
                if _card_fly(card_py, board, state["active_num"],
                             "inprogress", {"bug": reason}):
                    state["active_col"] = "inprogress"
                    state["active_has_shipped"] = False
                continue

            # Clean ship hit → fly to done
            ship = classify_ship(text, bool(files) or state["active_has_files"])
            if ship and state["active_col"] != "done":
                writeup = (state["active_has_shipped"]
                           and "patched" or "shipped (replay)")
                if _card_fly(card_py, board, state["active_num"], "done",
                             {"writeup": writeup}):
                    state["active_col"] = "done"
                    state["active_has_shipped"] = True
            continue

        if kind == "git_commit":
            if state["active_num"] is None:
                continue
            if state["active_col"] == "done":
                continue
            sha = (ev.get("meta") or {}).get("shaShort", "")
            if _card_fly(card_py, board, state["active_num"], "done",
                         {"writeup": f"commit {sha}"}):
                state["active_col"] = "done"
                state["active_has_shipped"] = True
            continue

        # memory_write / plan_write → log a subtask on active card
        if kind in ("memory_write", "plan_write"):
            if state["active_num"] is not None:
                _card_subtask(card_py, board, state["active_num"],
                              f"{kind.split('_')[0]}: {ev['text'][:50]}")
            continue

    print(f"✓ replayed {n_replayed} substantive turn(s) → board {board}",
          file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--board", type=Path, required=True,
                    help="board.json path to write cards into")
    ap.add_argument("--port", type=int, default=7894,
                    help="port the server is listening on")
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--turns-per-sec", type=float, default=10.0)
    ap.add_argument("--gap-speedup", type=float, default=None,
                    help="if set, preserve real idle gaps × speedup "
                         "(overrides --turns-per-sec)")
    ap.add_argument("--max-turns", type=int, default=0,
                    help="cap substantive turns processed (0 = unlimited)")
    ap.add_argument("--no-llm", action="store_true",
                    help="skip LLM rewrite, use only heuristic_title")
    args = ap.parse_args()

    os.environ["BOARD_SERVER"] = f"http://127.0.0.1:{args.port}"
    replay(args.project.resolve(), args.board.resolve(), args.port,
           args.days, args.turns_per_sec, args.gap_speedup, args.max_turns,
           use_llm=not args.no_llm)


if __name__ == "__main__":
    main()
