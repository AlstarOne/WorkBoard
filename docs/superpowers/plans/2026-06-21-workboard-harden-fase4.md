# WorkBoard Harden — Fase 4 Implementation Plan (laatste fase)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De README eerlijk en onderbouwd maken (experimenteel/pre-1.0-banner, benchmarks naar `docs/` met "gemeten vs. aspiratie", niet-waargemaakte claims weg, autostart-opt-in verwerkt) en een `CONTRIBUTING.md` toevoegen die de interne `#NNN`-kaart-ID-conventie uitlegt. Daarmee zijn alle 6 review-punten afgewerkt.

**Architecture:** Puur documentatie. `README.md` wordt getemperd en geherstructureerd; de grote benchmarktabellen verhuizen naar `docs/BENCHMARKS.md` met een duidelijke "gemeten vs. aspiratie"-scheiding; `CONTRIBUTING.md` is nieuw. Geen code, geen tests — wel: elke achterblijvende claim moet onderbouwd zijn (geen invented numbers; verifieer tegen bron).

**Tech Stack:** Markdown.

**Scope:** Fase 4 uit de spec. Fase 1–3 zitten in `main`. Dit is de laatste fase van het harden-traject (Fase 2b-testschulden blijven open als aparte follow-up).

## Global Constraints

- **Geen invented claims.** Elke achterblijvende bewering in README/BENCHMARKS moet te staven zijn (tegen code, `docs/TOKEN_BUDGET.md`, of de Research-studie). Bij twijfel: verwijderen of als aspiratie labelen.
- **Werkende links/afbeeldingen behouden.** Alle `docs/assets/*.gif|png`-referenties en bestaande doc-links die nog kloppen blijven werken; verhuisde inhoud krijgt een correcte nieuwe link.
- **Eerlijk over de fork.** Dit is een geharde fork van `malcolm1232/WorkBoard`; vermeld dat, claim niet meer dan waar is.
- **Reflecteer Fase 1–3:** autostart is nu opt-in (`--autostart`); er is een stdlib-testsuite + CI; `install.sh --dry-run` bestaat; `docs/INSTALL.md` bestaat.
- **Nooit naar `upstream` pushen**; alleen `origin` (AlstarOne-fork), branch `harden/fase4`.

---

## File Structure

- `README.md` (wijzigen) — status-banner, getemperde toon, benchmarks eruit (link naar `docs/BENCHMARKS.md`), niet-waargemaakte claims weg, autostart-opt-in, links naar `INSTALL.md`/`CONTRIBUTING.md`.
- `docs/BENCHMARKS.md` (nieuw) — de verhuisde token-efficiency-tabellen met expliciete "gemeten vs. aspiratie / peer-cijfers uit hun eigen publicaties"-kadering.
- `CONTRIBUTING.md` (nieuw) — de `#NNN`-kaart-ID-conventie + dev/test-instructies.

---

### Task 1: README temperen + benchmarks verhuizen

**Files:**
- Modify: `README.md`
- Create: `docs/BENCHMARKS.md`
- Read first: huidige `README.md` (volledig), `docs/INSTALL.md`, `docs/TOKEN_BUDGET.md`, `docs/COMPARISON.md` (om de benchmark-kadering correct over te nemen).

**Interfaces:** geen code. Behoud de feature-secties en GIF-referenties (die beschrijven echte features); verander alleen toon, claims en structuur.

- [ ] **Step 1: Maak `docs/BENCHMARKS.md` en verplaats de tabellen**

Knip de hele sectie "📊 Token-Efficiency Summary — WorkBoard vs mem0 · claude-mem · Letta · graphify" (README rond regel 101–166, alle vergelijkingstabellen) uit de README en plak 'm in een nieuw `docs/BENCHMARKS.md`. Zet bovenaan `BENCHMARKS.md` een eerlijke kadering, bijv.:

```markdown
# Token-efficiency benchmarks

> **Lees dit eerst.** WorkBoard's eigen cijfers zijn *gemeten* (echte recall + bootstrap
> tegen een bevroren snapshot van echte Claude-Code-historie). De peer-cijfers (mem0,
> claude-mem, Letta, graphify) komen uit **hun eigen gepubliceerde getallen of een
> losse sandbox-run**, niet uit een head-to-head op identieke hardware/queries.
> Behandel de absolute getallen als indicatief en de **reductie-percentages** als de
> robuustere vergelijking. De graphify-vergelijking is deels appels-met-peren (ander
> domein). Zie `docs/TOKEN_BUDGET.md` voor de meetmethode en `docs/COMPARISON.md` voor
> het knowledge-graph-vs-memory-store-kader.
```

Behoud de tabellen zelf (inhoud niet verzinnen/wijzigen), inclusief de bestaande voetnoten over meetmethode.

- [ ] **Step 2: README — status-banner + fork-vermelding**

Voeg vlak na de titel/badges (vóór `## Quick start`) een eerlijk statusblok toe, bijv.:

```markdown
> ⚠️ **Status: experimenteel — pre-1.0.** WorkBoard is jong en in actieve ontwikkeling.
> Dit is een *geharde fork* van [malcolm1232/WorkBoard](https://github.com/malcolm1232/WorkBoard)
> met een toegevoegde testsuite + CI, een veiligere netwerk-bind, en een transparantere
> installer (`install.sh --dry-run`). Vertrouw het nog niet als enige bron van waarheid
> voor belangrijk werk; probeer het eerst met `./install.sh --demo` of `--dry-run`.
```

- [ ] **Step 3: README — niet-waargemaakte claims verwijderen/herkaderen**

- Verwijder de zin "**Three months in, your board self-heals.**" (README ~regel 212) — dat is aspiratie, niet aantoonbaar (het project is weken oud). Behoud de feitelijke rest van die bullet (flock + rolling backups + `recover`/`repair-links`/`migrate`).
- Vervang de Token-Efficiency-sectie (nu verhuisd) door een korte, getemperde alinea + link, bijv.: "WorkBoard is ontworpen om **goedkoop te bouwen en te onderhouden** (0 model-calls om je werk te persisteren; de 130 KB+ `board.json` wordt nooit auto-geladen). Voor de gemeten cijfers vs. mem0 / claude-mem / Letta / graphify, zie [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md)." Laat de bestaande "Maar wat's the disadvantage?"-sectie staan (die is al eerlijk).
- Temper de duidelijkste superlatieven/marketing-emoji in de kop-secties (bijv. de tagline en de "watch your work come to life"-retoriek) naar iets nuchterders, **zonder** de feitelijke feature-beschrijvingen of GIF's te verwijderen. Niet de hele README ontdoen van persoonlijkheid — alleen overclaims terugbrengen.

- [ ] **Step 4: README — Fase 1–3 verwerken**

- **Autostart opt-in.** Pas elke plek aan die suggereert dat install automatisch autostart-bij-login registreert (Quick start / "Under the hood" / Optional Installation): autostart is nu **opt-in** via `--autostart`. De `launchd/systemd/Task Scheduler`-bullet (README ~regel 198) blijft beschrijven dát het kan, maar noteer dat het opt-in is.
- **Source-install URL.** Update de `git clone`-regel (~regel 29) naar de geharde fork: `git clone https://github.com/AlstarOne/WorkBoard`. Laat de marketplace-regel (malcolm1232) staan (dat is de plugin van de maker) maar maak duidelijk dat de fork de geharde variant is.
- **Nieuwe docs linken.** Voeg in "Learn more" links toe naar [`docs/INSTALL.md`](docs/INSTALL.md) ("exacte install-footprint + uninstall") en [`CONTRIBUTING.md`](CONTRIBUTING.md) ("bijdragen + de #-kaart-ID-conventie"). Noem kort dat er nu een stdlib-testsuite + GitHub Actions CI is.
- Verwijs in Quick start/Optional Installation naar `install.sh --dry-run` als manier om de footprint te zien zonder te installeren.

- [ ] **Step 5: Self-check + commits**

Lees de herschreven README + BENCHMARKS na: (a) geen kapotte links/afbeeldingen, (b) geen claim die je niet kunt staven, (c) toon is nuchter maar leesbaar. Dan:
```bash
git add docs/BENCHMARKS.md README.md
git commit -m "docs(readme): temper claims, move benchmarks to docs/BENCHMARKS.md, reflect opt-in autostart + tests/CI (#3)"
git push origin harden/fase4
```
(Docs raken CI niet; push voor back-up.)

---

### Task 2: `CONTRIBUTING.md`

**Files:**
- Create: `CONTRIBUTING.md`
- Read first: een paar `scripts/*.py` met `#NNN`-refs in comments (bijv. `_boardio.py`, `serve.py`) om de conventie correct te beschrijven; `.github/workflows/ci.yml`.

**Interfaces:** geen code; documentatie.

- [ ] **Step 1: Schrijf `CONTRIBUTING.md`**

Dek minimaal:
- **De `#NNN`-conventie.** Leg uit dat `#NNN`-verwijzingen in code-comments (bijv. `#609`, `#627`) **interne WorkBoard-kaart-ID's** zijn (uit het project's eigen board), **geen GitHub-issues**. Zo voorkom je dat lezers ze verwarren met issues en valse volwassenheid afleiden.
- **Lokaal draaien & testen.** `python -m unittest discover -s tests -p "test_*.py" -v` (pure stdlib, geen `pip install`). Noem dat de install-integratietest POSIX-only is (skip op Windows).
- **Zero-dependency regel.** Geen runtime- of test-dependencies toevoegen; alleen Python-standaardbibliotheek. CI draait op Linux + Windows × Python 3.9/3.12.
- **Branch/PR-workflow** kort (werk op een branch, tests groen + CI groen vóór merge).
- **Karakteriseringstests.** Nieuwe tests voor bestaand gedrag horen het echte gedrag vast te leggen, niet een assert te forceren.

- [ ] **Step 2: Commit + push**

```bash
git add CONTRIBUTING.md
git commit -m "docs: add CONTRIBUTING with the #NNN internal-card-id convention (#6)"
git push origin harden/fase4
```

---

## Self-Review

**1. Spec-dekking (Fase 4):**
- README experimenteel/pre-1.0-banner → Task 1 Step 2. ✅
- benchmarks naar `docs/` met "gemeten vs. aspiratie" → Task 1 Step 1 (`docs/BENCHMARKS.md`). ✅
- niet-waargemaakte claims weg ("3 months self-heals") → Task 1 Step 3. ✅
- superlatieven/emoji temperen → Task 1 Step 3. ✅
- autostart-opt-in in README → Task 1 Step 4. ✅
- `#NNN`-conventie → Task 2 (`CONTRIBUTING.md`). ✅
- (punt 1 jong/onbewezen: de banner + de in Fase 1–3 toegevoegde tests/CI/eerlijke docs dekken dit gezamenlijk.) ✅

**2. Placeholder-scan:** geen TBD/TODO; concrete inhoud + verplichte bronverificatie per stap. ✅

**3. Consistentie:** de README-links naar `docs/BENCHMARKS.md`, `docs/INSTALL.md`, `CONTRIBUTING.md` wijzen naar bestanden die deze fase aanmaakt of die al bestaan (INSTALL.md uit Fase 3). De autostart-opt-in-bewoording matcht Fase 3. ✅

**Opmerking voor de uitvoerder:** dit is een tonale herschrijving — temperen, niet slopen. Behoud feitelijke feature-beschrijvingen, GIF's en werkende links; verwijder alleen overclaims en verzin niets nieuws. Verifieer elk getal/claim dat je laat staan tegen de bron. Regelnummers zijn indicatief (README op `harden/fase4`); match op context.
