# Contributing to WorkBoard

Thanks for your interest in contributing. WorkBoard is an experimental, pre-1.0 project
— a hardened fork of [malcolm1232/WorkBoard](https://github.com/malcolm1232/WorkBoard)
with added tests, CI, a safer network bind, and a more transparent installer.
Contributions are welcome; please read this document before opening a pull request.

---

## The `#NNN` comment convention

You will see comments like `#609`, `#627`, `#102`, `#562` throughout the codebase:

```python
# rev-as-CAS (#609) prevents lost updates when two sessions write the same card
# #102 BOARD-AUTO-LINK — linkedFiles drive the PreToolUse flash hook.
```

**These are internal WorkBoard card IDs** — references to cards on the project's own
WorkBoard board, not GitHub issues. They record *why* a decision was made or which
card tracked the work. You will not find them in the GitHub issue tracker; that is
expected. Do not interpret a `#NNN` reference as evidence of a mature issue history
— the numbers simply come from the project's own in-progress board.

---

## Running the tests

WorkBoard's test suite uses **Python's standard library only** — no `pip install`
required.

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Run this from the repo root. All tests should pass before you open a pull request.

**Note:** the install integration test (`tests/test_install_dryrun.py`) is
**POSIX-only** and will be skipped automatically on Windows. All other tests run
on both platforms.

---

## Zero-dependency rule

WorkBoard has no runtime or test dependencies outside the Python standard library.
**Do not add any `import` that requires a `pip install`** — not in production code,
not in tests. If you need functionality that a third-party library would normally
provide, implement it with stdlib or open a discussion first.

This constraint is intentional: users can run the tool with any Python 3.9+
installation, no virtual environment setup required.

---

## CI matrix

Every push and pull request runs the full test suite on GitHub Actions across:

| OS | Python |
|---|---|
| Linux (ubuntu-latest) | 3.9 |
| Linux (ubuntu-latest) | 3.12 |
| Windows (windows-latest) | 3.9 |
| Windows (windows-latest) | 3.12 |

CI must be green before a PR is merged. The workflow file is
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## Branch and PR workflow

1. Create a branch off `main` (or off `harden/fase4` if you are building on top of
   current hardening work).
2. Write your changes. If you are fixing a bug, write a failing test first.
3. Run `python -m unittest discover -s tests -p "test_*.py" -v` locally — all tests
   must pass.
4. Open a pull request. CI runs automatically; do not merge until CI is green.
5. Keep PRs focused — one logical change per PR makes review and revert easier.

**Push only to `origin` (the AlstarOne fork).** Never push to `upstream`
(malcolm1232/WorkBoard).

---

## Characterization tests

When adding tests for existing behaviour (rather than a new feature), write
*characterization tests*: assert what the code *actually does*, not what you think
it should ideally do. The goal is to lock in the current behaviour so future
refactoring does not silently change it. If the current behaviour is wrong, fix the
behaviour first and then write the test against the corrected output.

---

## Learn more

- [`docs/INSTALL.md`](docs/INSTALL.md) — exact install footprint, uninstall steps,
  and `--dry-run` preview
- [`docs/TOKEN_BUDGET.md`](docs/TOKEN_BUDGET.md) — measured token cost breakdown
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — repo layout and internals
