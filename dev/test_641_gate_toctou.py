#!/usr/bin/env python3
"""#641 regression: the SessionStart recon gate must be re-checked UNDER recon_lock,
not only before it. reconcile_sweep grows a `gate` callable that is evaluated after
the lock is acquired — so a bootstrap fill that starts between the cheap pre-check
and the sweep can't be raced (the sweep stands down instead of shuffling cards into
a board that's actively re-streaming).

Run:  python3 dev/test_641_gate_toctou.py   →  exit 0 = all green, 1 = any fail.

LLM-free, live-board-free: a throwaway board with one candidate card, CLAUDECODE
unset (autonomous path so recon_lock is taken), and _llm_reconcile patched to a
flag so we can prove whether the sweep proceeded past the gate.

  G1  gate() → False  → sweep returns 0 and NEVER calls the LLM (TOCTOU closed).
  G2  gate() → True   → sweep proceeds to the LLM (gate open).
  G3  gate is None    → sweep proceeds (bootstrap callers unaffected).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import hourly_reconcile as R  # noqa: E402

_fails = 0


def check(cond: bool, msg: str) -> None:
    global _fails
    print(f"  {'✓' if cond else '✗'} {msg}")
    if not cond:
        _fails += 1


def _board_with_candidate(d: str) -> Path:
    board = Path(d) / "board.json"
    board.write_text(json.dumps({"cards": [
        {"num": 1, "id": "c-x", "column": "inprogress", "title": "live work",
         "tags": []},
    ]}))
    return board


def _run(gate, *, want_llm: bool, label: str):
    saved = R._llm_reconcile
    saved_env = os.environ.get("CLAUDECODE")
    os.environ.pop("CLAUDECODE", None)   # force the autonomous (recon_lock) path
    called = {"llm": False}

    def fake_llm(candidates, events, done_cards):
        called["llm"] = True
        return []   # no moves → sweep returns 0 cleanly

    R._llm_reconcile = fake_llm
    try:
        with tempfile.TemporaryDirectory() as d:
            board = _board_with_candidate(d)
            n = R.reconcile_sweep(Path("card.py"), board,
                                  [{"ts_ms": 1, "text": "x"}],
                                  only_discovered=False, gate=gate)
    finally:
        R._llm_reconcile = saved
        if saved_env is not None:
            os.environ["CLAUDECODE"] = saved_env

    check(n == 0, f"{label}: returns 0")
    check(called["llm"] is want_llm,
          f"{label}: LLM {'called' if want_llm else 'NOT called'} "
          f"(got called={called['llm']})")


if __name__ == "__main__":
    print("G1: gate False (replay began after pre-check) → skip under lock")
    _run(lambda: False, want_llm=False, label="gate-False")
    print("G2: gate True → proceeds")
    _run(lambda: True, want_llm=True, label="gate-True")
    print("G3: gate None (bootstrap callers) → proceeds")
    _run(None, want_llm=True, label="gate-None")
    print()
    if _fails:
        print(f"✗ {_fails} check(s) FAILED")
        sys.exit(1)
    print("✓ all #641 checks passed")
