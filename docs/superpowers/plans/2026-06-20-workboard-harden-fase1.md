# WorkBoard Harden — Fase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Een stdlib-`unittest` testfundament + GitHub Actions CI opzetten en daarmee meteen het `0.0.0.0`-zonder-token security-gat in `serve.py` via TDD dichten.

**Architecture:** Een nieuwe `tests/`-map met pure-stdlib `unittest`-tests (elke test zet zelf `scripts/` op `sys.path`). Een CI-workflow draait `python -m unittest discover` op Linux + Windows × Python 3.9/3.12. De security-fix wordt geïsoleerd in een pure helper `resolve_auth_token()` in `serve.py`, zodat de beslissing testbaar is zonder een echte server te starten.

**Tech Stack:** Python 3.9+ (alleen standaardbibliotheek), `unittest`, `unittest.mock`, GitHub Actions.

**Scope:** Dit plan dekt alleen **Fase 1** uit de spec (`docs/superpowers/specs/2026-06-20-workboard-harden-design.md`). Fase 0 (fork + remotes) is al uitgevoerd. Fase 2 (kern-dekking), Fase 3 (install-transparantie) en Fase 4 (docs) krijgen elk een eigen plan zodra we daar zijn.

## Global Constraints

- **Zero-dependency:** alleen Python-standaardbibliotheek. Geen `pip install`, geen pytest. Tests gebruiken `unittest`.
- **Cross-platform:** code en tests moeten op Linux én Windows draaien (de kern splitst `fcntl` vs `msvcrt`). CI dekt beide.
- **Python-floor:** 3.9 (zoals README claimt). Geen syntax die 3.9 niet kent.
- **Geen gedrag wijzigen zonder test:** elke gedragsverandering krijgt eerst een falende test.
- **Loopback-gedrag blijft ongewijzigd:** een default `127.0.0.1`-bind vereist nooit een token.
- **Nooit naar `upstream` pushen** (malcolm1232). Pushen mag alleen naar `origin` (AlstarOne-fork).

---

## File Structure

- `tests/test_boardio.py` (nieuw) — eerste echte test; valideert runner + import-pad tegen een pure functie in `_boardio.py`.
- `tests/test_auth.py` (nieuw) — tests voor de security-helper `resolve_auth_token()`.
- `.github/workflows/ci.yml` (nieuw) — CI: `unittest discover` op matrix Linux/Windows × 3.9/3.12.
- `scripts/serve.py` (wijzigen) — `import secrets`, een `--insecure-no-auth` vlag, de helpers `_is_loopback()` + `resolve_auth_token()`, en het inhaken daarvan op de auth-tokentoewijzing.

Elke test zet zelf `scripts/` op `sys.path` (bulletproof ongeacht hoe `discover` wordt aangeroepen); die ene regel herhalen we bewust per testbestand i.p.v. een gedeelde helper te importeren waarvan het import-pad weer van de discovery-modus afhangt.

---

### Task 1: Testfundament + CI

**Files:**
- Create: `tests/test_boardio.py`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: bestaande pure functie `_boardio._extract_rev(data: bytes) -> int` (geeft `int(json.loads(data)["rev"])`, of `0` bij parse-fout).
- Produces: een werkend testcommando `python -m unittest discover -s tests -p "test_*.py" -v` en een groene CI-pijplijn waar Task 2 op verder bouwt.

- [ ] **Step 1: Schrijf de eerste test (smoke-test tegen de kern)**

Create `tests/test_boardio.py`:

```python
"""Smoke-test: valideert dat de unittest-runner + het scripts/ import-pad werken,
door een pure functie uit de integriteits-kern te testen."""
import sys
import unittest
from pathlib import Path

# scripts/ importeerbaar maken — robuust ongeacht hoe `discover` draait.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _boardio  # noqa: E402


class ExtractRevTest(unittest.TestCase):
    def test_reads_rev_from_json_bytes(self):
        self.assertEqual(_boardio._extract_rev(b'{"rev": 7}'), 7)

    def test_missing_rev_defaults_to_zero(self):
        self.assertEqual(_boardio._extract_rev(b'{"cards": []}'), 0)

    def test_invalid_json_defaults_to_zero(self):
        self.assertEqual(_boardio._extract_rev(b'not json at all'), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Draai de test — verwacht PASS**

Run (vanuit repo-root `C:\Users\allar\Documents\Claude\WorkBoard`):
`python -m unittest discover -s tests -p "test_*.py" -v`
Expected: `Ran 3 tests` ... `OK`. (Dit test bestaand gedrag, dus het slaagt meteen — het bewijst dat runner + import-pad kloppen.)

- [ ] **Step 3: Voeg de CI-workflow toe**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ['3.9', '3.12']
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Run tests (stdlib unittest, no deps)
        run: python -m unittest discover -s tests -p "test_*.py" -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_boardio.py .github/workflows/ci.yml
git commit -m "test: stdlib unittest scaffold + GitHub Actions CI (Linux+Windows)"
```

- [ ] **Step 5: Push naar origin en verifieer CI groen**

```bash
git push origin harden/v1
gh run watch --exit-status
```
Expected: alle 4 matrix-jobs (ubuntu/windows × 3.9/3.12) slagen. Bij rood: open de logs met `gh run view --log-failed` en fix vóór Task 2.

---

### Task 2: Security-fix #4 — netwerk-bind nooit zonder token

**Files:**
- Create: `tests/test_auth.py`
- Modify: `scripts/serve.py:31` (voeg `import secrets` toe, alfabetisch tussen `import re` en `import subprocess`)
- Modify: `scripts/serve.py` (voeg `_is_loopback()` + `resolve_auth_token()` toe, vlak vóór `def _run_server`)
- Modify: `scripts/serve.py:815` (voeg `--insecure-no-auth` arg toe, direct na het `--auth-token` argument)
- Modify: `scripts/serve.py:1021` (vervang de directe toewijzing door een aanroep van `resolve_auth_token()`)

**Interfaces:**
- Consumes: `secrets.token_urlsafe` (stdlib); de bestaande `args.host`, `args.auth_token` en `BoardHandler.auth_token`.
- Produces: `serve.resolve_auth_token(host, explicit_token=None, insecure=False) -> str | None` — geeft het te handhaven token terug (of `None` voor "geen auth"). Loopback → `None`; netwerk-host zonder token → een nieuw `secrets.token_urlsafe(16)`-token; expliciet token → dat token; `insecure=True` → `None`.

- [ ] **Step 1: Schrijf de falende test**

Create `tests/test_auth.py`:

```python
"""Security: een netwerk-bind (0.0.0.0 / LAN-IP) mag nooit ongeauthenticeerd zijn."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import serve  # noqa: E402


class ResolveAuthTokenTest(unittest.TestCase):
    def test_explicit_token_always_wins(self):
        self.assertEqual(
            serve.resolve_auth_token("0.0.0.0", explicit_token="abc"), "abc")
        self.assertEqual(
            serve.resolve_auth_token("127.0.0.1", explicit_token="abc"), "abc")

    def test_loopback_needs_no_token(self):
        for host in ("127.0.0.1", "::1", "localhost"):
            self.assertIsNone(serve.resolve_auth_token(host))

    def test_network_bind_without_token_autogenerates(self):
        for host in ("0.0.0.0", "::", "192.168.1.50"):
            tok = serve.resolve_auth_token(host)
            self.assertIsInstance(tok, str)
            self.assertGreaterEqual(len(tok), 16)

    def test_insecure_flag_keeps_network_bind_open(self):
        self.assertIsNone(
            serve.resolve_auth_token("0.0.0.0", insecure=True))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Draai de test — verwacht FAIL**

Run: `python -m unittest tests.test_auth -v`
Expected: FAIL — `AttributeError: module 'serve' has no attribute 'resolve_auth_token'`.

- [ ] **Step 3: Implementeer de fix**

**3a.** In `scripts/serve.py`, voeg na `import re` (regel 31) toe:

```python
import secrets
```

**3b.** In `scripts/serve.py`, direct vóór `def _run_server(board_dir, args):` (regel ~1018), voeg toe:

```python
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", ""}


def _is_loopback(host: str) -> bool:
    """True als binden op `host` alleen de loopback-interface blootstelt.
    0.0.0.0 en :: binden ALLE interfaces (ook het LAN) → NIET loopback."""
    return host in _LOOPBACK_HOSTS


def resolve_auth_token(host, explicit_token=None, insecure=False):
    """Bepaal welk bearer-token de server moet afdwingen.

    - Een expliciet token (CLI/env) wint altijd.
    - Op een loopback-only bind is geen token nodig (lokaal; ongewijzigd gedrag).
    - Op een NETWERK-bind (0.0.0.0 / LAN-IP) zonder token: genereer er automatisch
      één, zodat het bord nooit ongeauthenticeerd op het netwerk staat.
      `insecure=True` (--insecure-no-auth) is de bewuste escape die het open laat.
    Geeft het te handhaven token terug, of None voor "geen auth".
    """
    if explicit_token:
        return explicit_token
    if _is_loopback(host):
        return None
    if insecure:
        return None
    return secrets.token_urlsafe(16)
```

**3c.** In `scripts/serve.py`, direct na het `--auth-token`-argument (eindigt op regel 815), voeg toe:

```python
    ap.add_argument("--insecure-no-auth", action="store_true",
                    help="Bewuste escape: laat een netwerk-bind (--host 0.0.0.0) "
                         "ZONDER token draaien. Standaard genereert WorkBoard "
                         "automatisch een token bij een netwerk-bind.")
```

**3d.** In `scripts/serve.py`, vervang regel 1021:

```python
    BoardHandler.auth_token = args.auth_token or None
```

door:

```python
    BoardHandler.auth_token = resolve_auth_token(
        args.host, args.auth_token, getattr(args, "insecure_no_auth", False))
    if BoardHandler.auth_token and not args.auth_token:
        print("🔒 netwerk-bind zonder token — automatisch een token gegenereerd; "
              "scan-URL volgt hieronder.", file=sys.stderr)
```

- [ ] **Step 4: Draai de tests — verwacht PASS**

Run: `python -m unittest tests.test_auth -v`
Expected: `Ran 4 tests` ... `OK`.

Run de hele suite ter controle: `python -m unittest discover -s tests -p "test_*.py" -v`
Expected: alle tests `OK`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_auth.py scripts/serve.py
git commit -m "fix(security): auto-generate auth token on network bind (#4)

A non-loopback bind (0.0.0.0 / LAN IP) without an explicit token now
auto-generates one via secrets.token_urlsafe, so the board is never exposed
unauthenticated. Loopback binds stay tokenless. --insecure-no-auth is the
deliberate escape. Covered by tests/test_auth.py."
```

- [ ] **Step 6: Push en verifieer CI groen**

```bash
git push origin harden/v1
gh run watch --exit-status
```
Expected: alle matrix-jobs groen.

---

## Self-Review

**1. Spec-dekking (Fase 1):**
- "stdlib unittest-suite" → Task 1 (`tests/test_boardio.py`) + Task 2 (`tests/test_auth.py`). ✅
- "GitHub Actions CI (Linux + Windows)" → Task 1, `.github/workflows/ci.yml`, matrix. ✅
- "0.0.0.0 zonder token: auto-genereer token via secrets.token_urlsafe; loopback blijft tokenloos; --insecure-no-auth escape" → Task 2, `resolve_auth_token()`. ✅
- "Eerst falende test, dan fix" → Task 2 stappen 1–4 (rood → groen). ✅
- Fases 2–4 zijn expliciet buiten scope (eigen plannen). ✅

**2. Placeholder-scan:** geen TBD/TODO/"handle edge cases"; alle code is volledig uitgeschreven. ✅

**3. Type-consistentie:** `resolve_auth_token(host, explicit_token=None, insecure=False)` heeft in Task 2's test (`test_auth.py`), de implementatie (3b) en de aanroep (3d) exact dezelfde naam en parameters. `_extract_rev` matcht de bestaande signatuur in `_boardio.py`. ✅

**Opmerking voor de uitvoerder:** regelnummers (31, 815, 1021) gelden voor de huidige `serve.py` op branch `harden/v1`; controleer de context (de getoonde omringende regels) i.p.v. blind op het nummer te vertrouwen, want eerdere stappen kunnen regels verschuiven.
