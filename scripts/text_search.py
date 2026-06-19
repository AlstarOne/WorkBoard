"""Lexical card matcher (#781 H1 — zero-dependency).

Score a free-text query ("i rmb last time I did the auth redirect…") against
each card's CURATED fields (title / code / tags / 140-char origin snippet) so
recall surfaces the right ENTRY POINTS cheaply — the agent/user then pulls
`card.py show <#>` for detail. Stdlib only (no embeddings, no vector DB) — that's
the whole point: deterministic, traceable, token-cheap.

This is the provisional default; #781's bake-off (recall@3 vs cost over the gold
queries) confirms or upgrades the scorer. Used by `card.py recall` today and the
future auto-recall UserPromptSubmit hook.
"""
from __future__ import annotations
import re
from difflib import SequenceMatcher

# Stopwords stripped from the query before matching (recall phrasings + filler).
_STOP = set(
    "the a an of to in on at and or for is are was were be been do does did done "
    "how why what which when where who whom that this these those it its my your our "
    "i we you he she they last time ago about with from into vs on-the over under "
    "remember rmb recall find search show me again still open close did-we what-did "
    "thing things stuff work worked working".split()
)


def _keywords(q: str) -> list[str]:
    toks = re.findall(r"#?[a-zA-Z0-9][a-zA-Z0-9_.-]*", q.lower())
    return [t for t in toks if t not in _STOP and (len(t) > 1 or t.startswith("#"))]


def _card_text(c: dict) -> str:
    parts = [
        c.get("title", "") or "",
        c.get("code", "") or "",
        " ".join(c.get("tags", []) or []),
        (c.get("origin", "") or "")[:140],
    ]
    return " ".join(p for p in parts if p).lower()


def score(query: str, card: dict) -> float:
    kws = _keywords(query)
    if not kws:
        return 0.0
    text = _card_text(card)
    title = (card.get("title", "") or "").lower()
    if not text:
        return 0.0
    # exact #N reference → near-certain hit
    ref = 0.0
    num = card.get("num")
    for k in kws:
        if k.startswith("#") and k[1:].isdigit() and num is not None and int(k[1:]) == num:
            ref = 6.0
    hits = sum(1 for k in kws if k in text)
    title_hits = sum(1 for k in kws if k in title)
    kw_frac = hits / len(kws)                                   # coverage of the query
    fuzzy = SequenceMatcher(None, " ".join(kws), text).ratio()  # catch near-spellings
    return ref + 2.0 * title_hits + 1.0 * hits + 0.8 * kw_frac + 0.4 * fuzzy


def rank(query: str, cards: list[dict], top: int = 3, min_score: float = 0.8):
    """Return [(score, card), …] for the top matches clearing min_score (so it
    stays SILENT when nothing is a real match). Sorted by score, then recency
    (higher card num) as the tiebreak."""
    scored = [(score(query, c), c) for c in cards]
    scored = [(s, c) for s, c in scored if s >= min_score]
    scored.sort(key=lambda x: (-x[0], -(x[1].get("num") or 0)))
    return scored[:top]
