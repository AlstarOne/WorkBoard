# WorkBoard Harden — Fase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De integriteits-kern van WorkBoard afdekken met stdlib-`unittest` karakteriseringstests: cross-process locking + backups (`_boardio`), sticky port-toewijzing (`port_registry`), rev-as-CAS lost-update-preventie (`card_state`), en de retry-ladder van de LLM-extractor (`hourly_extract_llm`).

**Architecture:** Vier nieuwe, op zichzelf staande testbestanden onder `tests/`, elk gericht op één module. Geen productiecode-wijziging verwacht — dit zijn *karakteriseringstests* die het huidige gedrag vastleggen zodat latere refactors veilig zijn. Elk testbestand zet zelf `scripts/` op `sys.path` en isoleert disk/omgeving via temp-dirs en env-var-overrides; de LLM-extractor wordt gemockt (geen echte `claude -p`).

**Tech Stack:** Python 3.9+ (alleen standaardbibliotheek), `unittest`, `unittest.mock`, `tempfile`.

**Scope:** Fase 2 uit de spec (`docs/superpowers/specs/2026-06-20-workboard-harden-design.md`). Fase 1 (testfundament, CI, security-fix) is afgerond en in `main`. Command-niveau tests voor `card.py`/`card_commands.py` (cmd_add/cmd_fly lifecycle, kolom-guards) zijn bewust UITGESTELD naar een latere Fase 2b — die hebben meer fixture-oppervlak (argparse-Namespaces, vier kolom-guards) en zijn brozer; Fase 2 dekt eerst de deterministische integriteits-primitieven. Fase 3 (install) en Fase 4 (docs) volgen daarna.

## Global Constraints

- **Zero-dependency:** alleen Python-standaardbibliotheek. Geen `pip install`, geen pytest.
- **Cross-platform:** tests draaien op Linux én Windows (CI dekt beide). Locking splitst `fcntl` vs `msvcrt` — houd lock-tests simpel en kort (korte timeouts).
- **Python-floor:** 3.9.
- **Geen echte neveneffecten:** nooit de echte `~/.board-steward` of een echte poort/het netwerk raken; nooit `claude -p` echt aanroepen (mock `subprocess`). Elke test gebruikt een temp-dir en ruimt op in `tearDown`.
- **Karakterisering, niet TDD-rood:** deze tests beschrijven *bestaand* gedrag en horen meteen te slagen. Slaagt een test niet, dan onthult dat ofwel een echte bug ofwel een verkeerde aanname — meld dat als `DONE_WITH_CONCERNS` i.p.v. de test te forceren.
- **Nooit naar `upstream` pushen** (malcolm1232); pushen alleen naar `origin` (AlstarOne-fork), branch `harden/fase2`.

---

## File Structure

- `tests/test_boardio_locking.py` (nieuw) — backups (`write_backup`/`_prune`/`list_backups`) + locks (`board_lock`, `recon_lock`).
- `tests/test_port_registry.py` (nieuw) — `assign` stickiness/preferred-conflict/GC + `write`/`lookup`/`remove`.
- `tests/test_card_state.py` (nieuw) — `atomic_save` rev-bump + `_assert_base_rev`/`BoardConflict` CAS + backup-neveneffect.
- `tests/test_extract_retry.py` (nieuw) — `extract_cards_for_chunk` foutmapping (`ChunkExtractionError` vs lege bucket) + `_extract_chunk_with_retries` split-recovery (alles gemockt).

Elk testbestand begint met de `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))`-regel (bewust per bestand herhaald, robuust ongeacht discovery-modus). Bestaand `tests/test_boardio.py` (Fase 1 smoke) blijft ongemoeid; locking/backups krijgen een eigen bestand.

---

### Task 1: `_boardio` — backups + locks

**Files:**
- Create: `tests/test_boardio_locking.py`

**Interfaces (bestaand, uit `scripts/_boardio.py`):**
- `write_backup(board_path, data: bytes, keep=BACKUP_KEEP)` → schrijft `<dir>/.backups/board-<rev>.json`, prunet tot newest `keep`. `BACKUP_KEEP == 10`.
- `list_backups(board_path)` → `[(rev:int, Path), ...]`, newest rev eerst.
- `board_lock(target, timeout=5.0)` → contextmanager, yield `True` bij acquire, `False` bij timeout.
- `recon_lock(board)` → contextmanager, non-blocking: yield `True` als vrij, `False` als al gehouden.

- [ ] **Step 1: Schrijf de tests**

Create `tests/test_boardio_locking.py`:

```python
"""Karakterisering van _boardio: backup-snapshots/pruning en cross-process locks."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _boardio  # noqa: E402


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.board = self.tmp / "board.json"
        self.board.write_text('{"rev": 1}')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_backup_creates_snapshot_named_by_rev(self):
        _boardio.write_backup(self.board, b'{"rev": 5}')
        snap = self.tmp / ".backups" / "board-5.json"
        self.assertTrue(snap.exists())
        self.assertEqual(snap.read_bytes(), b'{"rev": 5}')

    def test_prune_keeps_only_newest_N(self):
        for rev in range(1, 13):  # 12 snapshots; keep == 10
            _boardio.write_backup(self.board, json.dumps({"rev": rev}).encode())
        bdir = self.tmp / ".backups"
        revs = sorted(int(p.stem.split("-")[1]) for p in bdir.glob("board-*.json"))
        self.assertEqual(len(revs), _boardio.BACKUP_KEEP)
        self.assertEqual(revs, list(range(3, 13)))  # newest 10 = revs 3..12

    def test_list_backups_newest_first(self):
        for rev in (1, 2, 3):
            _boardio.write_backup(self.board, json.dumps({"rev": rev}).encode())
        revs = [r for r, _ in _boardio.list_backups(self.board)]
        self.assertEqual(revs, [3, 2, 1])


class LockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.board = self.tmp / "board.json"
        self.board.write_text("{}")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_board_lock_acquires_when_free(self):
        with _boardio.board_lock(self.board) as acquired:
            self.assertTrue(acquired)

    def test_board_lock_times_out_when_already_held(self):
        with _boardio.board_lock(self.board) as first:
            self.assertTrue(first)
            with _boardio.board_lock(self.board, timeout=0.2) as second:
                self.assertFalse(second)

    def test_recon_lock_is_non_blocking(self):
        with _boardio.recon_lock(self.board) as first:
            self.assertTrue(first)
            with _boardio.recon_lock(self.board) as second:
                self.assertFalse(second)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Draai de tests — verwacht PASS**

Run: `python -m unittest tests.test_boardio_locking -v`
Expected: 6 tests, `OK`. (Karakterisering — slaagt tegen huidige code. Mocht `test_board_lock_times_out_when_already_held` of `test_recon_lock_is_non_blocking` op een platform anders blijken: NIET de assert omdraaien — meld als `DONE_WITH_CONCERNS` met de waargenomen uitkomst per OS.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_boardio_locking.py
git commit -m "test: characterize _boardio backups, prune, and locks"
```

- [ ] **Step 4: Push en verifieer CI groen**

```bash
git push origin harden/fase2
gh run list --branch harden/fase2 --limit 3   # newest id → next line
gh run watch <id> --exit-status
```
Expected: 4-cell matrix groen. Bij rood (vaak een platformverschil in locking): `gh run view --log-failed`, beoordeel of het een echte platform-eigenaardigheid is, en meld het — pas geen assert aan om groen te forceren zonder dat te melden.

---

### Task 2: `port_registry.assign` — stickiness, preferred-conflict, GC

**Files:**
- Create: `tests/test_port_registry.py`

**Interfaces (bestaand, uit `scripts/port_registry.py`):**
- `assign(board_dir, preferred=None, lo=PORT_LO, hi=PORT_HI)` → `int`. Sticky per board-dir; `preferred` wordt genegeerd als al door een andere (bestaande) board-dir geclaimd; dode dirs (niet meer op disk) worden ge-GC't. `PORT_LO==7891`, `PORT_HI==7999`.
- `write(board_dir, port, pid)` / `lookup(board_dir) -> int|None` / `remove(board_dir)` op de liveness-registry.
- Env-overrides: `BOARD_REGISTRY`, `BOARD_ASSIGNMENTS`, `BOARD_ACTIVE`. **`board_dir` moet fysiek bestaan** (assign filtert op `Path(k).exists()`).

- [ ] **Step 1: Schrijf de tests**

Create `tests/test_port_registry.py`:

```python
"""Karakterisering van port_registry.assign + liveness-registry round-trip."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import port_registry  # noqa: E402


class PortRegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["BOARD_REGISTRY"] = str(self.tmp / "registry.json")
        os.environ["BOARD_ASSIGNMENTS"] = str(self.tmp / "assignments.json")
        os.environ["BOARD_ACTIVE"] = str(self.tmp / "last-active")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        for k in ("BOARD_REGISTRY", "BOARD_ASSIGNMENTS", "BOARD_ACTIVE"):
            os.environ.pop(k, None)

    def _board(self, name):
        d = self.tmp / name
        d.mkdir(exist_ok=True)
        return str(d)

    def test_assign_returns_port_in_range(self):
        port = port_registry.assign(self._board("a"))
        self.assertTrue(port_registry.PORT_LO <= port <= port_registry.PORT_HI)

    def test_assign_is_sticky_for_same_board(self):
        a = self._board("a")
        self.assertEqual(port_registry.assign(a), port_registry.assign(a))

    def test_preferred_taken_by_other_board_falls_through(self):
        a = self._board("a")
        self.assertEqual(
            port_registry.assign(a, preferred=port_registry.PORT_LO),
            port_registry.PORT_LO,
        )
        b = self._board("b")
        p_b = port_registry.assign(b, preferred=port_registry.PORT_LO)
        self.assertNotEqual(p_b, port_registry.PORT_LO)
        self.assertTrue(port_registry.PORT_LO <= p_b <= port_registry.PORT_HI)

    def test_dead_dir_is_gced_freeing_its_port(self):
        a = self.tmp / "a"
        a.mkdir()
        self.assertEqual(
            port_registry.assign(str(a), preferred=port_registry.PORT_LO),
            port_registry.PORT_LO,
        )
        shutil.rmtree(a)  # board dir verdwijnt van disk
        b = self._board("b")
        self.assertEqual(
            port_registry.assign(b, preferred=port_registry.PORT_LO),
            port_registry.PORT_LO,  # vrijgekomen poort herbruikt
        )

    def test_write_lookup_remove_roundtrip(self):
        a = self._board("a")
        port_registry.write(a, 7895, os.getpid())
        self.assertEqual(port_registry.lookup(a), 7895)
        port_registry.remove(a)
        self.assertIsNone(port_registry.lookup(a))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Draai de tests — verwacht PASS**

Run: `python -m unittest tests.test_port_registry -v`
Expected: 5 tests, `OK`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_port_registry.py
git commit -m "test: characterize port_registry assign stickiness, preferred-conflict, GC"
```

- [ ] **Step 4: Push en verifieer CI groen** (zelfde commando's als Task 1, branch `harden/fase2`).

---

### Task 3: `card_state.atomic_save` — rev-as-CAS

**Files:**
- Create: `tests/test_card_state.py`

**Interfaces (bestaand, uit `scripts/card_state.py`):**
- `load(p) -> dict`; `atomic_save(p, d, regen=True) -> int` (bumpt `d["rev"]` naar `base_rev+1`, schrijft atomisch, retourneert nieuwe rev).
- `_assert_base_rev(p, base_rev)` → raise `BoardConflict` als disk-rev != `base_rev` (None/onleesbaar = pass).
- `_current_rev(p) -> int|None`. `BoardConflict(Exception)`.
- Module-globals: `_HOLDING_LOCK` (zet `True` → direct-write pad, geen server/lock-acquire), `REGEN_SCRIPT` (overschrijf naar niet-bestaand pad → geen regen-subprocess). Env: `BOARD_NO_SERVER=1`.

- [ ] **Step 1: Schrijf de tests**

Create `tests/test_card_state.py`:

```python
"""Karakterisering van card_state.atomic_save: rev-as-CAS lost-update-preventie + backup."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import card_state  # noqa: E402

MINIMAL_BOARD = {
    "rev": 1, "nextNum": 1, "savedAt": "", "savedBy": "claude",
    "columns": [
        {"id": "task", "name": "Task", "kind": "todo", "stackUnder": None},
        {"id": "inprogress", "name": "In Progress", "kind": "active", "stackUnder": None},
        {"id": "done", "name": "Done", "kind": "done", "stackUnder": None},
    ],
    "cards": [],
}


class AtomicSaveCasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.board = self.tmp / "board.json"
        self.board.write_text(json.dumps(MINIMAL_BOARD))
        os.environ["BOARD_NO_SERVER"] = "1"
        card_state._HOLDING_LOCK = True
        card_state.REGEN_SCRIPT = self.tmp / "nope.py"  # bestaat niet → geen regen-subprocess

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("BOARD_NO_SERVER", None)
        card_state._HOLDING_LOCK = False

    def test_atomic_save_bumps_rev_and_returns_new_rev(self):
        d = card_state.load(self.board)
        new_rev = card_state.atomic_save(self.board, d)
        self.assertEqual(new_rev, 2)
        self.assertEqual(json.loads(self.board.read_text())["rev"], 2)

    def test_assert_base_rev_raises_on_mismatch(self):
        with self.assertRaises(card_state.BoardConflict):
            card_state._assert_base_rev(self.board, 99)

    def test_concurrent_bump_triggers_conflict(self):
        d = card_state.load(self.board)  # base rev 1
        other = json.loads(self.board.read_text())
        other["rev"] = 2  # een andere schrijver bumpt disk achter onze rug
        self.board.write_text(json.dumps(other))
        with self.assertRaises(card_state.BoardConflict):
            card_state.atomic_save(self.board, d)

    def test_current_rev_missing_file_returns_none(self):
        self.assertIsNone(card_state._current_rev(self.tmp / "absent.json"))

    def test_backup_written_on_save(self):
        d = card_state.load(self.board)
        card_state.atomic_save(self.board, d)
        self.assertTrue((self.tmp / ".backups" / "board-2.json").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Draai de tests — verwacht PASS**

Run: `python -m unittest tests.test_card_state -v`
Expected: 5 tests, `OK`. (Mocht `import card_state` falen of `REGEN_SCRIPT`/`_HOLDING_LOCK` anders heten dan verwacht: meld `DONE_WITH_CONCERNS` met de echte namen i.p.v. te gokken.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_card_state.py
git commit -m "test: characterize card_state rev-as-CAS conflict detection + backup"
```

- [ ] **Step 4: Push en verifieer CI groen** (zelfde commando's, branch `harden/fase2`).

---

### Task 4: `hourly_extract_llm` — retry-ladder (gemockt)

**Files:**
- Create: `tests/test_extract_retry.py`

**Interfaces (bestaand, uit `scripts/hourly_extract_llm.py`):**
- `extract_cards_for_chunk(chunk, project, timeout_s=90) -> list[dict]` — bouwt digest per bucket; lege digest → `[]` (geen subprocess); bij non-zero exit / non-JSON / subprocess-fout → raise `ChunkExtractionError`.
- `_extract_chunk_with_retries(chunk_keys, buckets, project, bucket_min) -> list[dict]` — schoon → geen retry; gefaalde multi-bucket chunk → split-in-half en herstel.
- `ChunkExtractionError(Exception)`. Mock-seams (alle in `hourly_extract_llm`-namespace): `build_digest`, `parse_card_array`, `subprocess`, en `extract_cards_for_chunk` zelf.

- [ ] **Step 1: Schrijf de tests**

Create `tests/test_extract_retry.py`:

```python
"""Karakterisering van hourly_extract_llm: ChunkExtractionError vs lege bucket + split-recovery.
Alle LLM-calls gemockt — er draait nooit een echte `claude -p`."""
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import hourly_extract_llm as hx  # noqa: E402


def _proc(returncode=0, stdout=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


class ExtractChunkTest(unittest.TestCase):
    def _chunk(self):
        return [("12:00", [{"ts": 1}])]

    def test_returns_cards_on_success(self):
        with mock.patch.object(hx, "build_digest", return_value="DIGEST"), \
             mock.patch.object(hx, "subprocess") as msub, \
             mock.patch.object(hx, "parse_card_array", return_value=[{"title": "x"}]):
            msub.SubprocessError = Exception
            msub.run.return_value = _proc(0, '[{"title": "x"}]')
            cards = hx.extract_cards_for_chunk(self._chunk(), Path("."))
        self.assertEqual(cards, [{"title": "x"}])

    def test_nonzero_exit_raises_chunk_error(self):
        with mock.patch.object(hx, "build_digest", return_value="DIGEST"), \
             mock.patch.object(hx, "subprocess") as msub:
            msub.SubprocessError = Exception
            msub.run.return_value = _proc(1, "")
            with self.assertRaises(hx.ChunkExtractionError):
                hx.extract_cards_for_chunk(self._chunk(), Path("."))

    def test_non_json_raises_chunk_error(self):
        with mock.patch.object(hx, "build_digest", return_value="DIGEST"), \
             mock.patch.object(hx, "subprocess") as msub, \
             mock.patch.object(hx, "parse_card_array", return_value=None):
            msub.SubprocessError = Exception
            msub.run.return_value = _proc(0, "not json")
            with self.assertRaises(hx.ChunkExtractionError):
                hx.extract_cards_for_chunk(self._chunk(), Path("."))

    def test_empty_digest_returns_empty_without_subprocess(self):
        with mock.patch.object(hx, "build_digest", return_value=""), \
             mock.patch.object(hx, "subprocess") as msub:
            cards = hx.extract_cards_for_chunk(self._chunk(), Path("."))
        self.assertEqual(cards, [])
        msub.run.assert_not_called()


class RetryLadderTest(unittest.TestCase):
    def test_clean_chunk_returns_without_retry(self):
        buckets = {0: [{"ts": 1}], 1: [{"ts": 2}]}
        with mock.patch.object(hx, "extract_cards_for_chunk",
                               return_value=[{"title": "ok"}]) as m:
            out = hx._extract_chunk_with_retries([0, 1], buckets, Path("."), 30)
        self.assertEqual(out, [{"title": "ok"}])
        self.assertEqual(m.call_count, 1)  # geen retry op een schone chunk

    def test_failed_multibucket_splits_and_recovers(self):
        buckets = {0: [{"ts": 1}], 1: [{"ts": 2}]}
        seen = []

        def side_effect(chunk, project):
            seen.append(chunk)
            if len(chunk) > 1:
                raise hx.ChunkExtractionError("multi")
            return [{"title": "half-%d" % len(seen)}]

        with mock.patch.object(hx, "extract_cards_for_chunk", side_effect=side_effect):
            out = hx._extract_chunk_with_retries([0, 1], buckets, Path("."), 30)
        self.assertEqual(len(out), 2)  # beide helften los hersteld


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Draai de tests — verwacht PASS**

Run: `python -m unittest tests.test_extract_retry -v`
Expected: 6 tests, `OK`. (Als een mock-seam niet bestaat onder die naam — bv. `parse_card_array`/`build_digest` zijn niet in `hx`-namespace — meld `DONE_WITH_CONCERNS` met de echte importstructuur i.p.v. te gokken.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_extract_retry.py
git commit -m "test: characterize hourly_extract_llm ChunkExtractionError + split-retry"
```

- [ ] **Step 4: Push en verifieer CI groen** (zelfde commando's, branch `harden/fase2`).

---

## Self-Review

**1. Spec-dekking (Fase 2 "kern-dekking"):**
- `_boardio` locking + backups → Task 1. ✅
- `card_state`/CAS rev-as-CAS → Task 3. ✅
- `port_registry` assign idempotent+sticky, bump → Task 2 (let op: code doet *fallthrough*, geen "bump" — de test legt het werkelijke gedrag vast en de spec-term "bump" is hier de fallthrough). ✅
- retry-ladder `hourly_extract_llm` → Task 4. ✅
- `card.py` command-niveau → expliciet UITGESTELD naar Fase 2b (gedocumenteerd in Scope). ✅ (bewuste afbakening, geen gat)

**2. Placeholder-scan:** geen TBD/TODO; alle testcode volledig uitgeschreven. ✅

**3. Type/naam-consistentie:** functienamen en globals (`write_backup`, `_prune` via `BACKUP_KEEP`, `list_backups`, `board_lock`, `recon_lock`, `assign`, `PORT_LO/HI`, `write`/`lookup`/`remove`, `atomic_save`, `_assert_base_rev`, `_current_rev`, `BoardConflict`, `_HOLDING_LOCK`, `REGEN_SCRIPT`, `extract_cards_for_chunk`, `_extract_chunk_with_retries`, `ChunkExtractionError`, mock-seams `build_digest`/`parse_card_array`/`subprocess`) komen uit de feitelijke broncode (Explore-mapping met file:line). ✅

**Opmerking voor de uitvoerder:** dit zijn karakteriseringstests tegen *bestaand* gedrag — ze horen meteen te slagen. Forceer nooit een assert om groen te krijgen; een onverwachte uitslag is signaal (echte bug of verkeerde aanname) en hoort als `DONE_WITH_CONCERNS` gemeld te worden. Twee tests met platform-risico (lock-timeout, recon-non-blocking) en de mock-seams in Task 4 zijn de meest waarschijnlijke plekken voor een verrassing.
