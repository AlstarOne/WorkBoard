# `/check` (recall) performance — does it fail fast, or loop?

**The worry:** if `/check` is invoked and *can't* find anything, does it hang/loop/
"load for 30s" — making it unusable? And how does it compare to Claude just finding
the answer itself?

**Method:** on the real 594-card board, time `card.py recall` end-to-end (subprocess
+ 1.3 MB board load + BM25, median of 5) for an **easy**, **medium/fuzzy**, and
**impossible/absent** query. Baseline = a **fresh Claude agent** finding the same
answer *without* recall (grep/read/reason) — wall-clock + tokens from each run.

## Results

| Difficulty | **WB `recall` (BM25)** | **Baseline: new Claude agent** | WB advantage |
|---|---|---|---|
| **Easy** (strong keywords) | **186 ms** · found ✓ · ~104 tok | 48.4 s · found ✓ · **29,295 tok** | **~260× faster · ~280× fewer tokens** |
| **Medium** (fuzzy paraphrase) | **187 ms** · found a related card ✓ | 36.2 s · found the exact card ✓ · 30,795 tok | **~194× faster** (agent more precise) |
| **Impossible** (absent topic) | **188 ms** · ⚠️ returned a *false* match | 35.2 s · correctly concluded **NO** · 33,836 tok | **~187× faster, but wrong** |

## Key findings

1. **`recall` cannot loop or hang. It is a single deterministic pass — ~187 ms, dead
   constant**, whether it finds the answer or not (186 / 187 / 188 ms across easy →
   impossible). There is no retry loop, no network, no model call. The "load for 30s"
   failure mode is **impossible** here.

2. **The 30-second risk is the *baseline*, not `recall`.** A fresh agent finding the
   answer itself took **35–48 s and ~30k tokens** every time. So `/check` is the
   *cure* for the slow-search problem — it replaces a 35 s, 30k-token agent hunt with
   a 0.19 s, ~100-token lookup (**~190–260× faster, ~300× cheaper**).

3. **The real gap is precision on *absent* queries, not speed.** On a topic that
   isn't on the board, `recall` returns a **weak false match** instead of going
   silent: 4 of 5 clearly-absent queries cleared the `min_score = 1.0` gate
   (scores 5–10). The agent baseline got these *right* (concluded "not found") — but
   took 35 s to do it. So today the trade is: **WB = fast but can surface a wrong
   card on an absent query; agent = slow but correctly says "not found."**

## Recommended fix (precision, not speed)

`min_score = 1.0` is too lenient on a large board — BM25 scores scale with corpus
size and query length, so a 5-word absent query accumulates several weak term hits
and clears a flat 1.0. Make the silence gate **relative/coverage-based** instead of a
flat constant, e.g.:
- require the top hit to cover a meaningful fraction of the query's content words
  (an absent query matches on *one* common word; a real query matches several /
  a literal), and/or
- gate on the **margin** between rank-1 and the median candidate score, and/or
- normalise the score by query length.

This keeps the fast medium/fuzzy matches while letting truly-absent queries go
**silent** — so an auto- or habit-invoked `/check` returns *nothing* rather than a
wrong card. (Recall already stays silent on empty / stopword / nonsense input; this
extends that to "no *relevant* match.")

## Verdict
The speed worry is fully resolved — `/check` is ~0.19 s flat and can't loop; it's
**the fix** for the 35 s self-search. Before leaning on it for *auto*-invocation,
tighten the silence gate so absent queries return nothing instead of a weak false
match. *(Card #795.)*
