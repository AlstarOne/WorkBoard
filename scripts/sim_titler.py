#!/usr/bin/env python3
"""sim_titler.py — title/code/notes rewriter for sim cards.

Hybrid C from the design:
  - heuristic_title()  strips conversational openers, extracts a noun cluster,
                       derives a short kebab/CAPS code. Used for short or
                       clearly trivial prompts.
  - llm_rewrite()      invokes `claude -p` headlessly with the prompt + the
                       nearest assistant context, asks for a JSON
                       {title, code, notes_summary}. Used when the prompt is
                       substantive (≥150 chars OR has urgency/work-verb).

Cached by sha256(prompt[:400]) so repeat sim runs are free after the first.
Cache lives at <board_dir>/sim_titler_cache.json (created on first hit).

Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

# ---------- heuristic_title -------------------------------------------------

# Conversational openers to strip (case-insensitive, anchored to start).
_OPENERS = [
    r"btw", r"oh wait", r"oh", r"wait", r"hmm", r"nvm",
    r"can u", r"can you", r"could u", r"could you",
    r"plz", r"please",
    r"okays?", r"ok", r"so", r"also", r"actually",
    r"i (think|want|guess|wonder|need)", r"lets?", r"lemme",
    r"u said", r"you said",
]
_OPENER_RE = re.compile(
    r"^(\s*(?:%s)\s*[,:\-—]*\s*)+" % "|".join(_OPENERS), re.I)

# Work-verb words — present-tense imperative + past participles + common
# user paraphrases ("change", "check", "make", "do").
_WORK_VERBS = re.compile(
    r"\b(add|build|ship|fix|refactor|rewrite|extract|wire|test|debug|"
    r"investigate|verify|migrate|deprecate|remove|delete|rename|deploy|"
    r"document|simplify|optimize|profile|measure|track|expose|surface|"
    r"implement|design|prototype|integrate|land|review|change|check|"
    r"make|do|run|create|enable|disable|move|merge|split|update|switch|"
    r"replace|reorder|sort|cleanup|clean|stop|start|restart)\b", re.I)

# Urgency markers — same as discover2.MANDATORY_RE.
_URGENCY = re.compile(
    r"\b(must|need to|needs to|gotta|urgent|critical|asap|p0|p1|blocker|"
    r"required|mandatory)\b", re.I)


def strip_openers(text: str) -> str:
    """Remove conversational opener(s) from the start of text."""
    return _OPENER_RE.sub("", text).strip()


def is_substantive(text: str) -> bool:
    """Should this prompt go to the LLM rewriter?"""
    t = text.strip()
    if len(t) >= 80:
        return True
    if _URGENCY.search(t):
        return True
    if _WORK_VERBS.search(t):
        return True
    # Question mark + ≥30 chars = likely a real question about the work
    if "?" in t and len(t) >= 30:
        return True
    return False


def heuristic_title(text: str, max_len: int = 70) -> tuple[str, str | None]:
    """Return (title, code). Cheap, no network."""
    body = strip_openers(text).split("\n", 1)[0]
    # Strip surrounding quotes / leading markdown.
    body = body.strip("'\"`> ")
    if not body:
        body = text.strip().split("\n", 1)[0]

    # Capitalize first letter unless it's a code-y token.
    title = body[:max_len].rstrip(".,;:!? ")
    if title and title[0].isalpha() and not title[:5].isupper():
        title = title[0].upper() + title[1:]

    # Derive a short code from noun-like tokens if a work-verb is present.
    code: str | None = None
    if _WORK_VERBS.search(body):
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", body.lower())
        stops = {"the", "and", "for", "with", "from", "into", "that",
                 "this", "what", "when", "where", "have", "has", "have",
                 "are", "was", "were", "but", "not", "can", "could",
                 "will", "would", "should", "shall", "make", "do", "does",
                 "did", "be", "been", "being", "i", "you", "u", "we",
                 "ur", "ya", "ok", "yes", "no", "btw"}
        nouns = [t for t in tokens if t not in stops and not _WORK_VERBS.match(t)]
        if nouns:
            code = "-".join(nouns[:3]).upper()[:30]
    return title, code


# ---------- llm_rewrite -----------------------------------------------------

_CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
_LLM_PROMPT = """\
You are titling a kanban card from a transcript turn. Read the user prompt and the assistant's nearby reply (for context — DO NOT title the reply, title the WORK the prompt initiates).

Output ONLY a single JSON object with these keys:
  title   — work-summary phrase, verb+noun, max 70 chars. Examples:
            "BOARD-FLY: atomic-hop primitive"
            "Fix card-drag freeze on iPhone"
            "Investigate convo dedup"
            Do NOT include the user's exact wording verbatim. NO quotes. NO conversational openers (btw, can u, oh wait).
  code    — short kebab or CAPS code derived from the noun cluster, max 24 chars. Examples: "BOARD-FLY", "DRAG-FREEZE-IPHONE", "DISCOVER2". Empty string if not a build/feature card.
  notes   — one-paragraph (~2 sentences) problem statement + fix direction, ≤200 chars. Empty string if there's not enough signal.

Return ONLY the JSON. No markdown, no commentary.
"""


def llm_rewrite(prompt_text: str, asst_context: str = "",
                timeout_s: int = 30) -> dict | None:
    """Invoke `claude -p` headlessly. Returns {title, code, notes} or None."""
    full = (
        f"{_LLM_PROMPT}\n\n"
        f"--- USER PROMPT ---\n{prompt_text[:1500]}\n\n"
        f"--- ASSISTANT CONTEXT (for context only) ---\n{asst_context[:1500]}\n"
    )
    try:
        proc = subprocess.run(
            [_CLAUDE_BIN, "-p", "--output-format", "text",
             "--model", "haiku"],
            input=full, capture_output=True, text=True, timeout=timeout_s,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    # The model sometimes wraps in ```json ... ``` — strip if so.
    out = re.sub(r"^```(?:json)?\s*", "", out)
    out = re.sub(r"\s*```\s*$", "", out)
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    title = (data.get("title") or "").strip()
    code = (data.get("code") or "").strip() or None
    notes = (data.get("notes") or "").strip()
    if not title:
        return None
    return {"title": title[:80], "code": code, "notes": notes[:240]}


# ---------- cache + dispatcher ---------------------------------------------

def _cache_path(board_dir: Path) -> Path:
    return board_dir / "sim_titler_cache.json"


def _load_cache(board_dir: Path) -> dict:
    p = _cache_path(board_dir)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save_cache(board_dir: Path, cache: dict) -> None:
    try:
        _cache_path(board_dir).write_text(json.dumps(cache, indent=2))
    except OSError:
        pass


def rewrite(prompt_text: str, asst_context: str = "",
            board_dir: Path | None = None, use_llm: bool = True) -> dict:
    """Public API. Always returns {title, code, notes}. Caches LLM hits."""
    text = prompt_text.strip()
    if not text:
        return {"title": "", "code": None, "notes": ""}

    # Cache key — first 400 chars of prompt is enough to identify.
    key = hashlib.sha256(text[:400].encode("utf-8")).hexdigest()[:16]
    cache: dict = _load_cache(board_dir) if board_dir else {}
    if key in cache:
        return cache[key]

    result: dict
    if use_llm and is_substantive(text):
        llm = llm_rewrite(text, asst_context)
        if llm:
            result = llm
        else:
            t, c = heuristic_title(text)
            result = {"title": t, "code": c, "notes": ""}
    else:
        t, c = heuristic_title(text)
        result = {"title": t, "code": c, "notes": ""}

    if board_dir:
        cache[key] = result
        _save_cache(board_dir, cache)
    return result


# ---------- pre-warm cache -------------------------------------------------

def _llm_for_prompt(prompt_text: str, asst_context: str) -> dict | None:
    """Worker: produce LLM result OR heuristic fallback."""
    llm = llm_rewrite(prompt_text, asst_context)
    if llm:
        return llm
    t, c = heuristic_title(prompt_text)
    return {"title": t, "code": c, "notes": ""}


def prewarm_cache(events: list[dict], board_dir: Path,
                  workers: int = 4, use_llm: bool = True,
                  progress_cb=None) -> dict[str, int]:
    """Pre-compute titles for all substantive prompts. Populates the cache
    file so the live replay only does cache lookups (no inline LLM stutter).

    events: pre-deduped, chronologically sorted (output of _flatten_events).
    Returns counters: {total, llm_called, heuristic_only, cached_hit}.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cache = _load_cache(board_dir)
    counters = {"total": 0, "llm_called": 0,
                "heuristic_only": 0, "cached_hit": 0}

    # Build a list of (key, prompt, asst_context, needs_llm) for unique prompts.
    work: list[tuple[str, str, str, bool]] = []
    seen: set[str] = set()
    for i, ev in enumerate(events):
        if ev["kind"] not in ("user_prompt", "convo_user"):
            continue
        text = (ev.get("text") or "").strip()
        if not text:
            continue
        # Skip trivials (the replayer won't card them anyway)
        from discover2 import is_trivial as _trivial
        if _trivial(text):
            continue
        key = hashlib.sha256(text[:400].encode("utf-8")).hexdigest()[:16]
        if key in seen:
            continue
        seen.add(key)
        counters["total"] += 1
        if key in cache:
            counters["cached_hit"] += 1
            continue
        # Look ahead a few events for asst context
        asst_ctx = ""
        for nx in events[i + 1: i + 5]:
            if nx["kind"] in ("asst_msg", "convo_asst") and nx.get("text"):
                asst_ctx = nx["text"][:1200]
                break
        needs_llm = use_llm and is_substantive(text)
        work.append((key, text, asst_ctx, needs_llm))

    if not work:
        return counters

    if progress_cb:
        progress_cb(0, len(work))

    # Heuristic-only items are instant — handle inline first.
    llm_jobs: list[tuple[str, str, str]] = []
    for key, text, asst_ctx, needs_llm in work:
        if not needs_llm:
            t, c = heuristic_title(text)
            cache[key] = {"title": t, "code": c, "notes": ""}
            counters["heuristic_only"] += 1
        else:
            llm_jobs.append((key, text, asst_ctx))

    # LLM jobs — fire in parallel.
    done = counters["heuristic_only"]
    if llm_jobs:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_llm_for_prompt, txt, ctx): key
                       for key, txt, ctx in llm_jobs}
            for fut in as_completed(futures):
                key = futures[fut]
                try:
                    result = fut.result()
                except Exception:
                    result = None
                if not result:
                    # Find original text by key (linear over llm_jobs)
                    for k, txt, _ in llm_jobs:
                        if k == key:
                            t, c = heuristic_title(txt)
                            result = {"title": t, "code": c, "notes": ""}
                            break
                cache[key] = result
                counters["llm_called"] += 1
                done += 1
                if progress_cb:
                    progress_cb(done, len(work))

    _save_cache(board_dir, cache)
    return counters


# ---------- CLI for ad-hoc testing -----------------------------------------

if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("text", nargs="?",
                    help="prompt text (defaults to stdin)")
    args = ap.parse_args()
    txt = args.text or sys.stdin.read()
    r = rewrite(txt, use_llm=not args.no_llm)
    print(json.dumps(r, indent=2))
