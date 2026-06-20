# WorkBoard — Harden v1 (design)

**Datum:** 2026-06-20
**Branch:** `harden/v1`
**Auteurs:** Allard (AlstarOne) + Claude
**Status:** ontwerp ter review

## Doel

Van de gekloonde WorkBoard (`malcolm1232/WorkBoard`, ~3,5 week oud, 560 commits,
één auteur, geen tests, geen CI) een **vertrouwde, eigen fork** maken die we als
basis voor onze samenwerking gebruiken. We werken de 6 review-punten systematisch
af, met een vangnet (tests + CI) als fundament en de hoogste-risico security-fix
vroeg.

Dit is een *harden*-traject, geen feature-traject: we voegen geen
WorkBoard-functionaliteit toe. We maken bestaand gedrag testbaar, veilig en
eerlijk gedocumenteerd, zonder de kernfilosofie (pure stdlib, zero-dependency,
100% lokaal) te breken.

## Uitgangspunten / constraints

- **Zero-dependency blijft heilig.** Eindgebruikers mogen geen `pip install`
  nodig hebben. Tests gebruiken daarom stdlib `unittest`, geen pytest. CI mag een
  kale Python gebruiken zonder extra packages.
- **Cross-platform.** De kern splitst bewust op POSIX `fcntl` vs. Windows
  `msvcrt`. CI moet daarom op zowel Linux als Windows draaien.
- **Geen gedrag wijzigen zonder dekking.** Elke gedragsverandering (security,
  install) krijgt eerst een test.
- **Niets pushen/publiceren zonder expliciete toestemming.** Fase 0 maakt een
  fork onder AlstarOne; verder lokaal werken op `harden/v1`.
- **Upstream-vriendelijk.** Wijzigingen blijven zo dat ze later als nette PR's
  terug naar `upstream` kunnen, mocht dat gewenst zijn.

## De 6 punten → concreet werk

| # | Review-punt | Concrete actie | Fase |
|---|-------------|----------------|------|
| 1 | Jong/onbewezen, 1 auteur, pre-1.0 | Geen losse fix — opgelost via tests + CI + eerlijke statusvermelding (samen met #2 en #3). | 1–4 |
| 2 | Geen tests | stdlib `unittest`-suite rond de integriteits-kern + GitHub Actions CI (Linux + Windows). | 1–2 |
| 4 | `0.0.0.0` zonder token | Bij non-loopback bind zonder token: `serve.py` **genereert automatisch** een token (`secrets.token_urlsafe`), activeert het en print de scan-URL — nooit ongeauthenticeerd op het netwerk. Loopback blijft tokenloos. Eerst falende test, dan fix. | 1 |
| 5 | Invasieve install-footprint | `install.sh`: `--dry-run`/preview, autostart opt-in i.p.v. default, nette uninstall, expliciete documentatie van alles wat het aanraakt (incl. per-turn contextkost van de UserPromptSubmit-hook). | 3 |
| 3 | README over-marketed | "Experimenteel / pre-1.0"-banner, benchmarktabellen naar `docs/` met "gemeten vs. aspiratie", superlatieven/emoji temperen, niet-waargemaakte claims ("3 months in, self-heals") verwijderen of herkaderen. | 4 |
| 6 | Misleidende `#`-refs | De `#NNN`-refs in comments zijn interne kaart-ID's, geen GitHub-issues. Conventie documenteren in `CONTRIBUTING.md`. | 4 |

## Aanpak

Gekozen: **A — vangnet eerst, maar security vroeg.** We bouwen eerst het
test-skelet + CI en trekken meteen de kleine, hoog-risico security-fix (#4) erin
via TDD. Daarna pas verbreden we de testdekking en raken we install/docs aan.

Afgewezen alternatieven:
- **B (quick wins eerst):** wijzigt security-gedrag met dunne dekking — te
  risicovol voor een data-integriteits-tool.
- **C (gebruik-en-hard parallel):** onsystematisch; past niet bij de gekozen
  harden-intentie.

## Faseplan

### Fase 0 — Fork & workspace
- `gh repo fork malcolm1232/WorkBoard` onder account **AlstarOne** (kopie van de
  default branch; we werken op `harden/v1`).
- Remotes: `origin` → AlstarOne-fork, `upstream` → `malcolm1232/WorkBoard`.
- `harden/v1` pusht naar `origin` (bestaat al lokaal).
- **Klaar als:** `git remote -v` toont beide remotes correct; `harden/v1` staat
  op de fork.

### Fase 1 — Testfundament + CI + security-fix (#2 deels, #4)
- Testmap `tests/` met stdlib `unittest`; runner-conventie (`python -m unittest
  discover`).
- GitHub Actions workflow `.github/workflows/ci.yml`: matrix Linux + Windows,
  Python 3.9 + 3.12, draait `unittest discover`. Geen externe deps.
- **TDD op #4:** test die aantoont dat `serve.py` op `--host 0.0.0.0` zónder token
  alles doorlaat (rood) → fix in `serve.py`: bij non-loopback bind zonder token
  auto-genereer een token (`secrets.token_urlsafe`), activeer het en print de
  scan-URL → test groen. Een bewuste `--insecure-no-auth` vlag blijft als
  expliciete escape. Loopback-gedrag (default) blijft ongewijzigd.
- **Klaar als:** CI groen op beide OS'en; security-test dekt zowel het geweigerde
  als het toegestane pad.

### Fase 2 — Kern-dekking uitbreiden (#1, #2)
Tests voor de ~1.640-regel integriteits-kern, in volgorde van risico:
- `_boardio.py`: `board_lock` (verkrijgen + time-out), `write_backup` +
  `_prune` (behoud nieuwste N), `list_backups`, `recon_lock` (non-blocking).
- `card_state.py` / `card.py`: atomic save-pad, rev-as-CAS (gelijktijdige schrijf
  verliest niets / faalt luid).
- `port_registry.py`: `assign` idempotent + sticky, bump bij bezette poort.
- `hourly_extract_llm.py`: retry-ladder — `ChunkExtractionError` vs. lege bucket,
  split-in-half, recursief re-bucketen (LLM-call gemockt; geen echte `claude -p`).
- **Klaar als:** kernpaden gedekt, CI groen, dekking gedocumenteerd in
  `docs/DEVELOPMENT.md`.

### Fase 3 — Install-transparantie (#5)
- `install.sh --dry-run`: print exact welke bestanden/hooks/services worden
  aangeraakt, schrijft niets.
- Autostart wordt **opt-in** (`--autostart`) i.p.v. default-aan.
- Geverifieerde uninstall (bestaande `scripts/uninstall.sh` nalopen/aanvullen).
- `docs/INSTALL.md`: precieze footprint — welke 5 hooks, welke poort, welke
  achtergrond-service per OS, en de per-turn contextkost van de
  UserPromptSubmit-hook.
- **Klaar als:** `--dry-run` klopt met wat een echte run doet; autostart gebeurt
  alleen op expliciete vlag.

### Fase 4 — Docs/perceptie (#3, #6)
- README: status-banner, claims temperen, benchmarktabellen → `docs/` met
  duidelijke "gemeten vs. aspiratie"-scheiding, niet-waargemaakte claims weg.
- `CONTRIBUTING.md`: leg de `#NNN` interne-kaart-ID-conventie uit.
- **Klaar als:** README bevat geen claim die we niet kunnen onderbouwen.

## Teststrategie

- **Framework:** stdlib `unittest`, ontdekt via `python -m unittest discover -s
  tests`.
- **Isolatie:** elke test gebruikt een tmp-board-dir (`tempfile.mkdtemp`); geen
  echte `~/.claude`, geen echte poorten waar mogelijk, geen netwerk.
- **Geen echte LLM-calls:** `subprocess.run` voor `claude -p` wordt gemockt
  (`unittest.mock`), zodat de retry-ladder deterministisch test.
- **Server-tests:** start de handler op een efemere poort op `127.0.0.1`; test de
  auth-gate-logica direct waar mogelijk i.p.v. via een echte socket.

## Risico's & mitigaties

- **Windows-locking (`msvcrt`) gedraagt zich anders dan `fcntl`.** → CI-matrix
  dekt beide; locking-tests draaien op beide OS'en.
- **Refactor breekt subtiel kerngedrag.** → Vangnet (Fase 1–2) vóór install/docs;
  geen gedragswijziging zonder test.
- **Upstream loopt door tijdens onze harden.** → `upstream` als remote behouden;
  periodiek rebasen indien gewenst.
- **Scope-creep richting features.** → Expliciet buiten scope: geen nieuwe
  WorkBoard-functionaliteit in dit traject.

## Buiten scope (nu)

- Nieuwe board-features, UI-herontwerp, extra fill-engines.
- Het daadwerkelijk *gebruiken* van WorkBoard voor onze samenwerking (kan later;
  dit traject maakt het daar eerst vertrouwd genoeg voor).
- Terugdragen naar upstream via PR (optie houden, nu niet doen).

## Definition of done (traject)

1. Fork onder AlstarOne, `harden/v1` erop, remotes correct.
2. CI groen op Linux + Windows; integriteits-kern gedekt door `unittest`.
3. `0.0.0.0`-zonder-token onmogelijk gemaakt, gedekt door test.
4. `install.sh` heeft `--dry-run` + opt-in autostart + gedocumenteerde footprint.
5. README is eerlijk en onderbouwd; `CONTRIBUTING.md` legt de `#`-conventie uit.
