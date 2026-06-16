#!/usr/bin/env python3
"""#643 regression: the direct (no-server) board write must rev-CAS like the
server POST path (#609), so a writer whose base rev went stale in the gap between
an UNLOCKED load and the self-locked write can't clobber the winner.

Run:  python3 dev/test_643_direct_cas.py   →  exit 0 = all green, 1 = any fail.

No server, no live board: a throwaway board.json + atomic_save with BOARD_NO_SERVER
so the self-lock direct path is exercised.

  C1  _assert_base_rev: raises on a moved rev, passes on a match, skips when the
      board can't be read (no false-conflict on first write).
  C2  atomic_save self-lock path: stale base (disk moved) → BoardConflict, NOT a
      clobber; matching base → writes rev+1.
  C3  atomic_save _HOLDING_LOCK path: matching base writes; moved rev raises.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import card_state as S  # noqa: E402

_fails = 0


def check(cond: bool, msg: str) -> None:
    global _fails
    print(f"  {'✓' if cond else '✗'} {msg}")
    if not cond:
        _fails += 1


def _board(d: str, rev: int) -> Path:
    p = Path(d) / "board.json"
    p.write_text(json.dumps({"rev": rev, "cards": []}))
    return p


def _disk_rev(p: Path) -> int:
    return json.loads(p.read_text())["rev"]


def test_assert_base_rev():
    print("C1: _assert_base_rev raise / pass / skip")
    with tempfile.TemporaryDirectory() as d:
        p = _board(d, 5)
        raised = False
        try:
            S._assert_base_rev(p, 4)   # disk=5, base=4 → conflict
        except S.BoardConflict:
            raised = True
        check(raised, "moved rev raises BoardConflict")

        ok = True
        try:
            S._assert_base_rev(p, 5)   # disk=5, base=5 → fine
        except S.BoardConflict:
            ok = False
        check(ok, "matching rev passes")

        missing = Path(d) / "gone.json"
        ok2 = True
        try:
            S._assert_base_rev(missing, 0)   # unreadable → skip (no raise)
        except S.BoardConflict:
            ok2 = False
        check(ok2, "unreadable board skips the check (no false-conflict)")


def test_self_lock_cas():
    print("C2: self-lock direct path CAS")
    saved_env = os.environ.get("BOARD_NO_SERVER")
    os.environ["BOARD_NO_SERVER"] = "1"   # force direct (no POST) path
    S._HOLDING_LOCK = False
    try:
        # (a) stale base: we loaded rev 5, but the disk moved to 6 → conflict.
        with tempfile.TemporaryDirectory() as d:
            p = _board(d, 6)
            stale = {"rev": 5, "cards": []}
            raised = False
            try:
                S.atomic_save(p, stale, regen=False)
            except S.BoardConflict:
                raised = True
            check(raised, "stale base → BoardConflict (no clobber)")
            check(_disk_rev(p) == 6, "disk rev untouched by the rejected write")

        # (b) matching base: writes rev+1.
        with tempfile.TemporaryDirectory() as d:
            p = _board(d, 5)
            fresh = {"rev": 5, "cards": []}
            rev = S.atomic_save(p, fresh, regen=False)
            check(rev == 6 and _disk_rev(p) == 6, "matching base writes rev 6")
    finally:
        if saved_env is None:
            os.environ.pop("BOARD_NO_SERVER", None)
        else:
            os.environ["BOARD_NO_SERVER"] = saved_env


def test_holding_lock_cas():
    print("C3: _HOLDING_LOCK direct path CAS")
    S._HOLDING_LOCK = True
    try:
        with tempfile.TemporaryDirectory() as d:
            p = _board(d, 5)
            rev = S.atomic_save(p, {"rev": 5, "cards": []}, regen=False)
            check(rev == 6 and _disk_rev(p) == 6, "matching base writes rev 6")

        with tempfile.TemporaryDirectory() as d:
            p = _board(d, 9)   # disk moved out from under the held lock
            raised = False
            try:
                S.atomic_save(p, {"rev": 5, "cards": []}, regen=False)
            except S.BoardConflict:
                raised = True
            check(raised, "moved rev under held lock raises (external writer)")
    finally:
        S._HOLDING_LOCK = False


if __name__ == "__main__":
    test_assert_base_rev()
    test_self_lock_cas()
    test_holding_lock_cas()
    print()
    if _fails:
        print(f"✗ {_fails} check(s) FAILED")
        sys.exit(1)
    print("✓ all #643 checks passed")
