#!/usr/bin/env python3
"""measure_digest.py — #299 DIGEST-COMPACT measurement harness.

Harvests the real /Users/malco activity, buckets it exactly as the production
path does, and reports:
  1. baseline vs compacted token/char totals (same-harvest A/B) + safety checks
  2. per-SOURCE token contribution (jsonl / convo / git / memory / plans / …),
     so each stream's cost is identifiable and exportable.

Run before/after touching digest_compact.py to report the actual % saved.
Token estimate = chars / 4; chars are reported too so the % is exact.

Usage: python3 scripts/measure_digest.py [days]
"""
from __future__ import annotations
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hourly_extractor as HE
import digest_compact

PROJECT = Path("/Users/malco")


def harvest(days: int):
    events = HE._flatten_events(PROJECT, days)
    buckets: dict[int, list[dict]] = {}
    for ev in events:
        buckets.setdefault(HE._bucket_hour(ev["ts"], 60), []).append(ev)
    return events, buckets


def combined_digest(buckets: dict) -> str:
    """Mirror _emit_extraction_pending: per-bucket build_digest with ONE shared
    seen-set across all buckets (main Claude reads every chunk in one context)."""
    sections, seen = [], set()
    for k in sorted(buckets.keys()):
        d = HE.build_digest(buckets[k], PROJECT, seen_heads=seen)
        if d.strip():
            sections.append(f"=== BUCKET {HE._bucket_label(k, 60)} ===\n{d}")
    return "\n\n".join(sections)


def line_breakdown(digest: str) -> Counter:
    c = Counter()
    for ln in digest.splitlines():
        s = ln.strip()
        if not s: c["(blank)"] += 1
        elif s.startswith("=== BUCKET"): c["bucket-header"] += 1
        elif "USER:" in s: c["USER"] += 1
        elif "CLAUDE edited:" in s: c["CLAUDE-edited"] += 1
        elif "CLAUDE:" in s: c["CLAUDE-head"] += 1
        elif "COMMIT" in s: c["COMMIT"] += 1
        elif "MEMORY:" in s: c["MEMORY"] += 1
        elif "PLAN:" in s: c["PLAN"] += 1
        else: c["other"] += 1
    return c


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    events, buckets = harvest(days)

    os.environ["DIGEST_COMPACT"] = "0"   # compact_enabled() reads env per call
    base = combined_digest(buckets)
    os.environ["DIGEST_COMPACT"] = "1"
    comp = combined_digest(buckets)

    bc, cc = len(base), len(comp)
    print(f"=== DIGEST MEASURE — {days}d harvest, project={PROJECT} ===")
    print(f"events harvested : {len(events)}   buckets: {len(buckets)}")
    print(f"                    {'BASELINE':>12}   {'COMPACTED':>12}   delta")
    print(f"  digest chars  : {bc:>12,}   {cc:>12,}   -{bc-cc:,} ({100*(bc-cc)/max(bc,1):.1f}%)")
    print(f"  ~tokens (/4)  : {bc//4:>12,}   {cc//4:>12,}   -{(bc-cc)//4:,}")
    print(f"  lines         : {base.count(chr(10))+1:>12,}   {comp.count(chr(10))+1:>12,}")
    print("--- line-type breakdown (baseline → compacted) ---")
    bb, cb = line_breakdown(base), line_breakdown(comp)
    for k in sorted(set(bb) | set(cb), key=lambda x: -bb.get(x, 0)):
        print(f"  {k:16s} {bb.get(k,0):6,} → {cb.get(k,0):6,}")

    # ---- per-SOURCE token contribution (targetable / exportable) ----
    # Cost of consuming ONLY each source, compacted, standalone — the number you'd
    # use to decide which streams to target or export.
    print("--- per-source contribution (compacted, standalone) ---")
    rows = []
    for src in HE.SOURCES:
        sb: dict[int, list[dict]] = {}
        for ev in events:
            if ev.get("source") == src:
                sb.setdefault(HE._bucket_hour(ev["ts"], 60), []).append(ev)
        if not sb:
            continue
        d = combined_digest(sb)
        rows.append((src, sum(1 for e in events if e.get("source") == src), len(d)))
    tot = sum(r[2] for r in rows) or 1
    for src, n, ch in sorted(rows, key=lambda r: -r[2]):
        print(f"  {src:10s} events={n:5,}  ~tok={ch//4:7,}  ({100*ch/tot:4.1f}% of source-sum)")

    bset = set(base.splitlines())
    notfound = [l for l in comp.splitlines() if l not in bset]
    def protected(l):
        s = l.strip()
        return any(t in s for t in ("USER:", "CLAUDE edited:", "COMMIT",
                                    "MEMORY:", "PLAN:")) or s.startswith("=== BUCKET")
    bp = Counter(l for l in base.splitlines() if protected(l))
    cp = Counter(l for l in comp.splitlines() if protected(l))
    print("--- safety checks ---")
    print(f"  lossless (compacted lines not byte-identical in baseline): {len(notfound)}")
    print(f"  hard-gate (protected USER/COMMIT/edited/MEMORY/PLAN dropped): "
          f"{sum(bp[l]-cp[l] for l in bp if bp[l] > cp[l])}")
    bdir = PROJECT / "Desktop/WorkBoard/board"
    (bdir / f"_digest_base_{days}d.txt").write_text(base)
    (bdir / f"_digest_comp_{days}d.txt").write_text(comp)
    print(f"--- digests written → board/_digest_base_{days}d.txt + _comp_{days}d.txt ---")


if __name__ == "__main__":
    main()
