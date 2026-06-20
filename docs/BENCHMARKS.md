# Token-efficiency benchmarks

> **Read this first.** WorkBoard's own figures are *measured* (real recall + bootstrap
> against a frozen snapshot of real Claude Code history). The peer figures (mem0,
> claude-mem, Letta, graphify) come from **their own published numbers or a single
> sandbox run**, not from a head-to-head test on identical hardware and queries.
> Treat the absolute numbers as indicative and the **reduction percentages** as the
> more robust comparison. The graphify comparison is partly apples-to-oranges (different
> domain: code knowledge graph vs. work-outcome tracking). See `docs/TOKEN_BUDGET.md`
> for the measurement methodology and `docs/COMPARISON.md` for the
> knowledge-graph-vs-memory-store framing.

---

## Why is WorkBoard cheaper?

1. **Carding is inline — zero extra model calls.** WorkBoard writes the card *during*
   your normal turn: the agent runs a deterministic `card.py` command and the writeup
   is text it already produced — **no separate session, no extra inference pass.** mem0,
   claude-mem and Letta instead spin up a **dedicated model call** to remember
   (claude-mem compresses *every* session via a ~5K-token call) — pure overhead on top
   of your normal usage.
2. **It doesn't run on every turn.** Unlike Letta (memory re-sent every turn) and the
   per-session extractors, WorkBoard writes **only when there's something to record**.
3. **No "full dump."** Even when it records, it never dumps your entire history — it
   writes **only what's needed**, so it never burns extra tokens.
4. **What it saves is structured, not a blob** — each card carries:
   - **Title** — a one-line overview, for fast future retrieval
   - **Origin / why it exists** (+ **Notes**) — the context behind it
   - **Writeup** — once it's done, *how* it was done (commits, files)
5. **Recall is a cheap tree-walk.** An agent finds a past workflow by traversing the
   graph — reading the **title** first, the description *only if needed* → **origin /
   why** → **how it was done** — a handful of tokens, never a re-read of everything.

*[**Read the full study here →**](../Research/token_comparison/MASTER_SUMMARY.md)*

**How it works:** WorkBoard's figures are *measured* (its real recall + real bootstrap,
run against a frozen snapshot of real Claude Code history); each peer comes from its own
published numbers or a real sandboxed run. **What the rows mean:**

- **Build the memory** — the one-time cost to turn your *past* history into memory.
- **Persist / session** — the ongoing cost to *save* each new session's work.
- **Live loop *(100 sessions × 3 recalls)*** — persist **+** recall combined over a
  project's life; the real steady-state cost.
- **Per single recall** — tokens to answer *one* question.
- **Recall vs full-context *(26K)*** — savings vs pasting your whole ~26,000-token
  history into every prompt (the naive baseline mem0's *"90%"* is measured against).
- *(Letta)* **In-context memory / turn** — memory re-sent on **every** turn ·
  *(graphify)* **Always-on / prompt** + **SKILL.md on engage** — per-prompt and
  on-engagement load.

---

## WorkBoard vs mem0

| Axis | WorkBoard (WB) | mem0 | Winner |
|---|--:|--:|:--|
| Build the memory | 64,162 Tok | 5,095,769 Tok | **WB 98.7% cheaper** |
| Persist / session | **0 model calls** | 1 LLM extract call (~5,462 Tok) + embed | **WB (free)** |
| Live loop *(100 sessions × 3)* | 719,700 Tok | 1,086,200 Tok | **WB 33.7% cheaper** |
| Per single recall | 2,399 Tok | 1,800 Tok | mem0 *(leaner)* |
| Recall vs full-context *(26K)* | 90.8% fewer | 93.1% fewer | ~tie |

## WorkBoard vs claude-mem

| Axis | WorkBoard (WB) | claude-mem | Winner |
|---|--:|--:|:--|
| Build the memory | ~10,546 Tok | 5,095,769 Tok | **WB ~99% cheaper** |
| Persist / session | **0 model calls** | 1 compression call *(full tier)* | **WB (free)** |
| Live loop *(100 sessions × 3)* | 719,700 Tok | 1,517,300 Tok | **WB 52.6% cheaper** |
| Per single recall | 2,399 Tok | 3,237 Tok | **WB 25.9% cheaper** |
| Backfill past history | mines your history | forward-only *(no bulk command)* | **WB** |

## WorkBoard vs Letta (MemGPT)

| Axis | WorkBoard (WB) | Letta | Winner |
|---|--:|--:|:--|
| In-context memory / turn | 306 Tok *(0 carried)* | 3,444 Tok *(blocks + tool schemas + prompt)* | **WB** |
| Persist / session | **0 model calls** | LLM tool-call per write + compaction | **WB** |
| Live loop *(100 × 50 × 3)* | 2,259,400 Tok *(929,400 trimmed)* | 11,909,200 Tok | **WB 81.0% cheaper** |
| Per single recall | 2,399 Tok | 1,064 Tok | Letta *(leaner)* |

## WorkBoard vs graphify *(code knowledge-graph — different domain)*

| Axis | WorkBoard (WB) | graphify | Winner |
|---|--:|--:|:--|
| Always-on / prompt | 306 Tok | 61 Tok *(cached)* | graphify |
| SKILL.md on engage | 5,898 Tok | 8,245 Tok *(+9,704 refs)* | **WB 28.5% cheaper** |
| Per recall | 2,399 Tok *(work Qs)* | 1,374 Tok *(code Qs)* | different questions |
| Write / keep current | 0 | 0 | tie |
| Big artifact autoload | never | never | tie |

> *WorkBoard's "Build the memory" figure varies with harvest config (hourly bucket size)
> — both shown are **under 1.3% of the peer's** per-session compression total, so the
> **reduction %** is the robust number.*

The 130 KB+ `board.json` is **never auto-loaded** — context stays clean no matter how
big the board grows.
