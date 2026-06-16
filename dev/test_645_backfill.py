#!/usr/bin/env python3
"""#645 regression: a bootstrap that dropped buckets (#640 records them as
`failed_buckets` + `partial:true` + `bucket_min` in .replay_state.json) must
AUTO-BACKFILL on the next SessionStart — re-extract the recorded buckets,
emit the recovered cards, and clear them from the gate so the loop converges.

Run:  python3 dev/test_645_backfill.py   →  exit 0 = all green, 1 = any fail.

LLM-free, live-board-free fault injection: we patch the harvest seam
(_flatten_events / _filter_events), the extraction seam (extract_cards_for_chunk
in the leaf namespace), and emit_card, then drive _backfill_failed_buckets
against a throwaway board + replay-state and assert:

  B1  a recorded bucket that now extracts OK is recovered (cards emitted) and
      CLEARED from failed_buckets; a bucket that STILL fails stays recorded; a
      bucket whose source events aged out of the harvest is DROPPED (converges).
  B2  partial flips OFF only when nothing remains failing.
  B3  no-op guards: not-partial / empty failed_buckets / replay-in-progress
      → no harvest, no emit, state untouched.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import hourly_extractor as H       # noqa: E402  (_backfill_failed_buckets lives here)
import hourly_extract_llm as L     # noqa: E402  (extraction seam after #646 split)

_fails = 0
BUCKET_MIN = 60


def check(cond: bool, msg: str) -> None:
    global _fails
    print(f"  {'✓' if cond else '✗'} {msg}")
    if not cond:
        _fails += 1


def _ts_for_bucket(key: int) -> datetime:
    """A real ts that lands in bucket `key` (sub-bucket retries read ev['ts'])."""
    return datetime.fromtimestamp(key * BUCKET_MIN * 60 + 60, tz=timezone.utc)


def _ev(key: int, fail: bool = False) -> dict:
    e = {"ts": _ts_for_bucket(key)}
    if fail:
        e["FAIL"] = True
    return e


def _write_state(board: Path, **kw) -> Path:
    p = board.parent / ".replay_state.json"
    state = {"completed_card_replay": 1, "bucket_min": BUCKET_MIN}
    state.update(kw)
    p.write_text(json.dumps(state))
    return p


def _patched_extract(chunk, project, timeout_s=90):
    """Succeed unless any event in the chunk carries a FAIL marker."""
    if any(ev.get("FAIL") for _, evs in chunk for ev in evs):
        raise L.ChunkExtractionError(chunk[0][0])
    return [{"title": f"recovered {chunk[0][0]}"}]


def test_backfill_recovers_clears_drops():
    print("B1/B2: recover OK bucket, keep failing one, drop aged-out one")
    # Three recorded failures: A recovers, B still fails, C has no source events.
    now_key = H._bucket_hour(datetime.now(timezone.utc), BUCKET_MIN)
    A, B, C = now_key - 2, now_key - 3, now_key - 5
    harvested = [_ev(A), _ev(B, fail=True)]   # C absent → aged out

    with tempfile.TemporaryDirectory() as d:
        board = Path(d) / "board.json"
        board.write_text("{}")
        p = _write_state(board, partial=True, failed_buckets=[A, B, C])

        saved = {n: getattr(H, n) for n in ("_flatten_events", "_filter_events",
                                            "emit_card")}
        saved_L = L.extract_cards_for_chunk
        emitted = []
        H._flatten_events = lambda *a, **k: list(harvested)
        H._filter_events = lambda events, *a, **k: events
        H.emit_card = lambda card_py, board, card, *a, **k: (emitted.append(card)
                                                             or len(emitted))
        L.extract_cards_for_chunk = _patched_extract
        try:
            H._backfill_failed_buckets(Path("/tmp/wb645-proj"), board)
        finally:
            for n, v in saved.items():
                setattr(H, n, v)
            L.extract_cards_for_chunk = saved_L

        st = json.loads(p.read_text())
        check(len(emitted) == 1, f"1 card recovered+emitted (got {len(emitted)})")
        check(st["failed_buckets"] == [B],
              f"only the still-failing bucket remains (got {st['failed_buckets']})")
        check(st["partial"] is True, "partial stays true while one bucket fails")
        check("backfilled_at" in st, "backfill stamped backfilled_at")
        check(st["completed_card_replay"] == 1, "gate stays open (#384)")


def test_backfill_full_recovery_clears_partial():
    print("B2: full recovery flips partial OFF")
    now_key = H._bucket_hour(datetime.now(timezone.utc), BUCKET_MIN)
    A, B = now_key - 2, now_key - 3
    harvested = [_ev(A), _ev(B)]   # both recover

    with tempfile.TemporaryDirectory() as d:
        board = Path(d) / "board.json"
        board.write_text("{}")
        p = _write_state(board, partial=True, failed_buckets=[A, B])

        saved = {n: getattr(H, n) for n in ("_flatten_events", "_filter_events",
                                            "emit_card")}
        saved_L = L.extract_cards_for_chunk
        emitted = []
        H._flatten_events = lambda *a, **k: list(harvested)
        H._filter_events = lambda events, *a, **k: events
        H.emit_card = lambda *a, **k: emitted.append(1) or len(emitted)
        L.extract_cards_for_chunk = _patched_extract
        try:
            H._backfill_failed_buckets(Path("/tmp/wb645-proj"), board)
        finally:
            for n, v in saved.items():
                setattr(H, n, v)
            L.extract_cards_for_chunk = saved_L

        st = json.loads(p.read_text())
        check(len(emitted) == 2, f"both buckets recovered (got {len(emitted)})")
        check(st["failed_buckets"] == [], "no buckets left failing")
        check(st["partial"] is False, "partial flipped OFF on full recovery")


def test_backfill_noops():
    print("B3: no-op guards never harvest or emit")
    now_key = H._bucket_hour(datetime.now(timezone.utc), BUCKET_MIN)

    def _run(label, **state_kw):
        with tempfile.TemporaryDirectory() as d:
            board = Path(d) / "board.json"
            board.write_text("{}")
            _write_state(board, **state_kw)
            touched = {"harvest": False, "emit": False}
            saved = {n: getattr(H, n) for n in ("_flatten_events", "emit_card")}
            H._flatten_events = lambda *a, **k: touched.__setitem__("harvest", True) or []
            H.emit_card = lambda *a, **k: touched.__setitem__("emit", True) or 1
            try:
                H._backfill_failed_buckets(Path("/tmp/wb645-proj"), board)
            finally:
                for n, v in saved.items():
                    setattr(H, n, v)
            check(not touched["harvest"] and not touched["emit"],
                  f"{label} → no harvest, no emit")

    _run("not-partial", partial=False, failed_buckets=[now_key - 1])
    _run("empty failed_buckets", partial=True, failed_buckets=[])
    _run("replay in progress", partial=True, failed_buckets=[now_key - 1],
         completed_card_replay=0)


if __name__ == "__main__":
    test_backfill_recovers_clears_drops()
    test_backfill_full_recovery_clears_partial()
    test_backfill_noops()
    print()
    if _fails:
        print(f"✗ {_fails} check(s) FAILED")
        sys.exit(1)
    print("✓ all #645 checks passed")
