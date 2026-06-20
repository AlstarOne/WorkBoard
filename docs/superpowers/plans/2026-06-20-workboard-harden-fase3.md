# WorkBoard Harden — Fase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De install-footprint transparant en minder invasief maken: `install.sh --dry-run` (plan-en-stop, schrijft niets), autostart opt-in (`--autostart` i.p.v. standaard-aan), volledige footprint-documentatie, en een veilige/transparante uninstall.

**Architecture:** `install.sh` krijgt een `--dry-run` die ná argument- en projectresolutie maar vóór elke side-effect een exact overzicht afdrukt en met exit 0 stopt — geen skill-symlink, geen hooks, geen poort-registry-write, geen server, geen autostart. Autostart wordt standaard uitgezet en alleen met `--autostart` aangezet. Een POSIX-only integratietest draait `bash install.sh --dry-run` in een geïsoleerde temp-`HOME` en bewijst dat er niets geschreven wordt. `docs/INSTALL.md` documenteert de exacte footprint; `scripts/uninstall.sh` krijgt een spiegelende `--dry-run`.

**Tech Stack:** Bash (`install.sh`, `uninstall.sh`), Python 3.9+ stdlib `unittest`/`subprocess` voor de integratietest, Markdown voor docs.

**Scope:** Fase 3 uit de spec (`docs/superpowers/specs/2026-06-20-workboard-harden-design.md`). Fase 1 (tests/CI/security) en Fase 2 (kern-dekking) zitten in `main`. De README-tekst die autostart-bij-install adverteert wordt in **Fase 4** bijgewerkt (niet hier). Fase 2b-testschulden (zie dat plan) blijven open.

## Global Constraints

- **Zero-dependency:** alleen stdlib voor de test; geen pip/pytest. De installer blijft pure bash + Python-stdlib.
- **Cross-platform install-test is POSIX-only:** `install.sh` is een bash-script; de integratietest draait alleen waar `bash` bestaat en `os.name != "nt"` (op Windows-CI overgeslagen, niet gefaald).
- **`--dry-run` schrijft NIETS:** geen bestand, hook, service, poort-registry-entry of server. Exit 0.
- **Autostart is opt-in:** standaard `DO_AUTOSTART=0`; alleen `--autostart` zet 'm aan. `--no-autostart` blijft als no-op (back-compat).
- **Geen gedrag wijzigen zonder test** voor het `--dry-run` / autostart-opt-in-gedrag.
- **Nooit naar `upstream` pushen**; alleen `origin` (AlstarOne-fork), branch `harden/fase3`.

---

## File Structure

- `install.sh` (wijzigen) — `DRY` + `--dry-run`, `--autostart` opt-in (default-flip `DO_AUTOSTART=1`→`0`), dry-run-rapportblok, picker-guard, autostart-bewoording, help-tekst.
- `tests/test_install_dryrun.py` (nieuw) — POSIX-only integratietest: `--dry-run` schrijft niets + rapporteert de footprint; autostart opt-in zichtbaar in het rapport.
- `docs/INSTALL.md` (nieuw) — exacte footprint: hooks, poort, achtergrond-service per OS, per-turn contextkost van de UserPromptSubmit-hook, en uninstall.
- `scripts/uninstall.sh` (wijzigen) — `--dry-run` + verificatie dat skill/hooks/autostart/server allemaal verwijderd worden.

---

### Task 1: `install.sh` — `--dry-run` + autostart opt-in

**Files:**
- Modify: `install.sh`
- Create: `tests/test_install_dryrun.py`

**Interfaces / anchors (huidige `install.sh`):**
- `set -euo pipefail` (regel 32); defaults blok rond `DO_AUTOSTART=1` (regel 50); arg-loop met `--no-autostart) DO_AUTOSTART=0; shift ;;` (regel 68); `usage() { sed -n '2,30p' ... }` (regel 57, drukt de header-comment 2–30 af); projectpicker-`if` (rond regel 132, conditie bevat `[ "$PROJECT" = "$HOME" ]`); Sectie 1 skill (regel 164); Sectie 4 autostart (rond regel 267); slot-bericht (rond regel 285).

- [ ] **Step 1: Schrijf de falende test**

Create `tests/test_install_dryrun.py`:

```python
"""Integratie: install.sh --dry-run schrijft NIETS en rapporteert de footprint.
POSIX-only — install.sh is een bash-script; op Windows overgeslagen."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTALL = REPO / "install.sh"
_BASH = shutil.which("bash")
_PY = shutil.which("python3") or shutil.which("python")


@unittest.skipIf(os.name == "nt" or _BASH is None or _PY is None,
                 "needs bash + python on a POSIX host")
class InstallDryRunTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.project = self.home / "proj"
        self.project.mkdir()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def _run(self, *extra):
        env = dict(os.environ)
        env["HOME"] = str(self.home)
        env["CLAUDE_CONFIG_DIR"] = str(self.home / ".claude")
        return subprocess.run(
            [_BASH, str(INSTALL), "--dry-run", "--no-open",
             "--project", str(self.project), *extra],
            cwd=str(REPO), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=60)

    def test_dry_run_exits_zero_and_writes_nothing(self):
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.home / ".claude" / "skills" / "board-steward").exists())
        self.assertFalse((self.home / ".claude" / "settings.json").exists())
        self.assertFalse((self.project / "board").exists())

    def test_dry_run_reports_footprint(self):
        out = self._run().stdout.lower()
        self.assertIn("dry-run", out)
        self.assertIn("hook", out)
        self.assertIn("autostart", out)

    def test_autostart_is_opt_in_by_default(self):
        out = self._run().stdout.lower()
        self.assertIn("skipped", out)  # autostart skipped tenzij --autostart

    def test_autostart_flag_enables_in_report(self):
        out = self._run("--autostart").stdout.lower()
        self.assertIn("login service", out)  # geactiveerd pad rapporteert de service


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Draai de test — verwacht FAIL**

Run: `python -m unittest tests.test_install_dryrun -v`
Expected: FAIL — `install.sh` kent nog geen `--dry-run` (de arg-loop eindigt op `*) echo "unknown arg"; exit 2`), dus exit code 2 → `test_dry_run_exits_zero_and_writes_nothing` faalt. (Draait de test op Windows, dan SKIP — verifieer 'm op een POSIX-host of laat CI-ubuntu het bewijzen.)

- [ ] **Step 3: Implementeer de install.sh-wijzigingen**

**3a. Default-flip + DRY-vlag.** In het defaults-blok: verander `DO_AUTOSTART=1` in `DO_AUTOSTART=0` en voeg een regel toe (bij de andere vlaggen):
```bash
DRY=0
```

**3b. Arg-parsing.** In de `while`-loop, voeg twee cases toe (naast `--no-autostart`):
```bash
    --dry-run) DRY=1; shift ;;
    --autostart) DO_AUTOSTART=1; shift ;;
```
Laat `--no-autostart) DO_AUTOSTART=0; shift ;;` staan (no-op back-compat).

**3c. Help-tekst.** In de header-comment die `usage()` afdrukt (regels 2–30), voeg bij de voorbeeld-invocaties twee regels toe, bijv. na de bestaande `./install.sh`-voorbeelden:
```bash
#     ./install.sh --dry-run            # PRINT exactly what it would do, write NOTHING
#     ./install.sh --autostart          # also register a login service (opt-in; off by default)
```

**3d. Picker overslaan in dry-run.** In de projectpicker-`if`-conditie (rond regel 132), voeg `[ "$DRY" = "0" ]` toe zodat de interactieve picker niet draait bij `--dry-run`. Bijvoorbeeld de conditie begint met `if [ "$DEMO" = "0" ] && ...` → voeg `&& [ "$DRY" = "0" ]` toe.

**3e. Dry-run-rapportblok.** Voeg dit blok toe DIRECT NA de projectpicker-sectie en VÓÓR `# ---- 1. skill` (regel 164), zodat het stopt vóór elke side-effect (vóór de skill-symlink én vóór de `port_registry.assign`-write in Sectie 2):
```bash
# ---- dry-run: report the footprint, write nothing, exit ----------------------
if [ "$DRY" = "1" ]; then
  CFG_BASE="${CLAUDE_CONFIG_DIR:-${HOME}/.claude}"
  echo
  say "DRY-RUN — what a real install would do (nothing below is written):"
  echo "  1. skill     → symlink ${REPO}"
  echo "               → ${CFG_BASE}/skills/board-steward"
  echo "  2. hooks     → wire the board-steward hooks (SessionStart, UserPromptSubmit,"
  echo "                 PreToolUse, Stop, SubagentStop) into ${CFG_BASE}/settings.json"
  echo "  3. server    → bootstrap a board in ${PROJECT}"
  echo "               → serve on http://127.0.0.1:${PORT} (sticky per-project port)"
  if [ "$DO_AUTOSTART" = "1" ]; then
    echo "  4. autostart → register a login service (launchd / systemd / Task Scheduler)"
  else
    echo "  4. autostart → SKIPPED (opt-in — re-run with --autostart to enable)"
  fi
  if [ "$OPEN_BROWSER" = "1" ]; then
    echo "  5. browser   → open http://127.0.0.1:${PORT}"
  fi
  echo
  ok "DRY-RUN complete — no files, hooks, services, ports, or servers were created."
  exit 0
fi
```

**3f. Autostart-bewoording.** Pas in Sectie 4 de `else`-tak en het slotbericht zo aan dat duidelijk is dat autostart opt-in is. In de `else`-tak van de autostart-`if` (rond regel 273–274) waar nu staat dat het wordt overgeslagen wegens `--no-autostart`, maak de default-melding:
```bash
    warn "autostart not registered (opt-in — pass --autostart to enable)"
```
(Laat de demo-specifieke melding intact als die er is; dit betreft de niet-demo default.)

- [ ] **Step 4: Draai de tests — verwacht PASS**

Run: `python -m unittest tests.test_install_dryrun -v`
Expected: 4 tests PASS op een POSIX-host (of SKIP op Windows). Draai ook de volledige suite: `python -m unittest discover -s tests -p "test_*.py" -v` → alles `OK` (30 bestaande + 4 nieuwe, minus de skips op Windows).

- [ ] **Step 5: Commit**

```bash
git add install.sh tests/test_install_dryrun.py
git commit -m "feat(install): --dry-run plan-and-stop + autostart opt-in (#5)"
```

- [ ] **Step 6: Push en verifieer CI groen**

```bash
git push origin harden/fase3
gh run list --branch harden/fase3 --limit 3   # newest id → next line
gh run watch <id> --exit-status
```
Expected: ubuntu-jobs draaien de install-test (groen); windows-jobs SKIPpen 'm (ook groen). Bij rood: `gh run view --log-failed`, beoordeel, fix.

---

### Task 2: `docs/INSTALL.md` — exacte footprint

**Files:**
- Create: `docs/INSTALL.md`
- Read first (om accuraat te documenteren): `scripts/install_hooks.py` (welke hooks/events exact gewired worden), `hooks/hooks.json`, `scripts/install_autostart.py` (per-OS mechanisme), `scripts/serve.py` (poort), `install.sh` (de net toegevoegde `--dry-run`/`--autostart`).

**Interfaces:** geen code; puur documentatie die de werkelijke installer-acties weerspiegelt. Verifieer elke claim tegen de bron (geen aannames).

- [ ] **Step 1: Schrijf `docs/INSTALL.md`**

Dek minimaal:
- **Eén-commando install** en wat het precies doet (verwijs naar `install.sh --dry-run` om het zelf te zien zonder te installeren).
- **Hooks** — exact welke Claude Code hook-events board-steward wired (uit `hooks/hooks.json` / `install_hooks.py`: SessionStart, UserPromptSubmit, PreToolUse, Stop, SubagentStop), met per hook één regel wat 'ie doet en — belangrijk — dat de **UserPromptSubmit-hook op elke prompt context injecteert** (de per-turn contextkost; noem de orde van grootte uit de README/SKILL als die er staat, anders beschrijf het kwalitatief en verwijs naar de bron).
- **Poort & server** — `127.0.0.1:7891` (sticky per project), pure stdlib, geen framework.
- **Achtergrond-service (autostart)** — per OS het mechanisme (launchd / systemd / Task Scheduler), en dat dit nu **opt-in** is (`--autostart`).
- **Wat er op disk verandert** — skill-symlink-pad, `settings.json`-pad, `board/`-map in het project, `~/.board-steward/` registry.
- **Verwijderen** — verwijs naar `scripts/uninstall.sh` (+ `--dry-run`, na Task 3).

- [ ] **Step 2: Self-check + commit**

Lees `INSTALL.md` na tegen de bron; corrigeer elke claim die niet klopt. Dan:
```bash
git add docs/INSTALL.md
git commit -m "docs(install): document exact install footprint + per-turn hook cost (#5)"
```

- [ ] **Step 3: Push** (`git push origin harden/fase3`). (Docs raken CI niet, maar push voor back-up + consistentie.)

---

### Task 3: `scripts/uninstall.sh` — transparante/veilige uninstall

**Files:**
- Modify: `scripts/uninstall.sh`
- Read first: huidige `scripts/uninstall.sh` (wat verwijdert het nu?), `scripts/install_hooks.py --uninstall...`, `scripts/install_autostart.py` (heeft het een uninstall-pad?).

**Interfaces:** spiegelt Task 1 — een `--dry-run` die opsomt wat verwijderd zou worden zonder iets te verwijderen, en verificatie dat skill + hooks + autostart-service + (lopende) server alle vier gedekt zijn.

- [ ] **Step 1: Inventariseer**

Lees `scripts/uninstall.sh`. Stel vast wat het verwijdert (skill-symlink? hooks uit settings.json? autostart-service? lopende server op de poort?) en noteer eventuele gaten. Als een van de vier ontbreekt, vul aan met de juiste verwijderstap (gebruik dezelfde scripts als install: `install_hooks.py --uninstall-hooks`, `install_autostart.py` uninstall-pad indien aanwezig).

- [ ] **Step 2: Voeg `--dry-run` toe**

Voeg een `--dry-run` toe die exact opsomt wat verwijderd zou worden (skill-pad, settings.json-hooks, service, server-poort) en met exit 0 stopt zonder iets te verwijderen — symmetrisch met `install.sh --dry-run`.

- [ ] **Step 3: Verifieer handmatig (geen echte uninstall op je systeem)**

Run de dry-run in een geïsoleerde temp-`HOME`/`CLAUDE_CONFIG_DIR` (zoals de install-test) en bevestig: exit 0, niets verwijderd, en het rapport noemt alle vier de componenten. Documenteer het commando + de output in het taakrapport. (Geen unittest vereist tenzij triviaal toe te voegen; een dry-run-rookcheck volstaat.)

- [ ] **Step 4: Commit + push**

```bash
git add scripts/uninstall.sh
git commit -m "feat(uninstall): --dry-run + verify skill/hooks/autostart/server coverage (#5)"
git push origin harden/fase3
```

---

## Self-Review

**1. Spec-dekking (Fase 3 install-transparantie):**
- `install.sh --dry-run` (print exact, schrijf niets) → Task 1 (plan-en-stop blok + test). ✅
- autostart opt-in i.p.v. default → Task 1 (default-flip + `--autostart`). ✅
- nette uninstall → Task 3 (`uninstall.sh --dry-run` + coverage-verificatie). ✅
- documenteer footprint + per-turn contextkost UserPromptSubmit → Task 2 (`docs/INSTALL.md`). ✅
- README-tekst over autostart → expliciet UITGESTELD naar Fase 4 (gedocumenteerd in Scope). ✅

**2. Placeholder-scan:** geen TBD/TODO; de test- en bash-code zijn volledig uitgeschreven. Task 2/3 beschrijven concrete inhoud + verplichte bronverificatie (geen "vul maar in"). ✅

**3. Consistentie:** de dry-run-test (`test_install_dryrun.py`) verwacht exact de markers die het rapportblok in 3e produceert: "dry-run", "hook", "autostart", "skipped" (default), "login service" (met `--autostart`). De default-flip (`DO_AUTOSTART=0`) is wat "skipped" in de default-run veroorzaakt. ✅

**Opmerking voor de uitvoerder:** regelnummers (32/50/57/68/132/164/267) gelden voor de huidige `install.sh` op `harden/fase3`; match op de getoonde context, niet blind op nummer. De dry-run-test is POSIX-only — verwacht SKIP op Windows-CI (dat is groen, geen falen). Als install.sh onder `set -euo pipefail` op een onverwachte plek stopt vóór het dry-run-blok (bijv. `PY=$(command -v python3 || command -v python)` op een host zonder python), is dat een echte vondst — meld het i.p.v. de test te verzwakken.
