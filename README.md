# WorkBoard

**A live kanban board your Claude Code agent keeps up to date for you — so you never lose an idea or a half-finished task.**

![Version](https://img.shields.io/badge/version-0.9.21-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![For Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-8A2BE2)

<!-- Drop a screenshot or GIF of the live board here: docs/assets/board-screenshot.png -->
<!-- ![The WorkBoard live board](docs/assets/board-screenshot.png) -->

---

Working with an AI agent, ideas pile up fast — and they slip away just as fast. You mention something mid-session, three tangents happen, and it's gone. Branching to-do lists make it worse: task 1 spawns 1.1, which spawns 1.1.1, and task 5 quietly gets forgotten three levels deep.

**WorkBoard fixes that.** It gives Claude a live board it keeps in sync *on its own* — every idea, task, and shipped change becomes a **card** in real time. Mention an idea and it's saved. Start work and the card slides to *In Progress*. Ship it and Claude writes a summary and moves it to *Done*. You just glance at the board at `http://127.0.0.1:7891` and see the whole state of your work — you never have to ask *"did you update the board?"*

## Why you'll like it

- 💡 **Never lose an idea.** Say *"I have an idea: add dark mode"* and a card appears instantly (with a 5-second Undo). It's captured whether or not you act on it now.
- 🔗 **Just say "Do #123."** Every card has a number. Reference it any time and Claude picks the work up exactly where it left off — no re-explaining.
- 🤖 **Tracked end-to-end.** Work auto-moves *Task → In Progress → Done*, with a written ship summary (what changed, which files, how it was verified) on every card.
- 🧠 **Recall months later, cheaply.** Three months on, ask *"what did we do on auth in May?"* Claude traverses the cards at minimal token cost instead of re-reading whole files or chat logs.
- ⚡ **Open it already full.** On day one, *History Replay* mines your past Claude sessions and flies your recent work onto the board — so you start with context, not an empty page.

## Quick start

**Install the plugin** (recommended):

```
/plugin marketplace add malcolm1232/WorkBoard
/plugin install board-steward@workboard
```

**Or one command from a clone:**

```bash
./install.sh                      # set up + bootstrap a board in the current project
./install.sh --project ~/code/foo # ...in a specific project
./install.sh --demo               # isolated dry-run — try it without touching anything
```

Then open **http://127.0.0.1:7891**. That's it — no account, no cloud, no config.

## What it feels like

```
You:     I have an idea: add dark mode to the settings page
Claude:  ✦ carded as #142 (Ideas)

…later…

You:     ok, do #142
Claude:  ✦ #142 → In Progress … shipped ✓  (#142 → Done, write-up attached)
```

## How it works

- **The board stays in sync by itself.** Bundled Claude Code hooks card work as it happens, so the board can't silently drift mid-session.
- **The board is the source of truth — not chat memory.** Claude reads it at session start, updates it as it works, and signs off at session end. Nothing gets dropped between sessions.
- **Token-cheap by design.** Claude reads a tiny digest first, then queries only the cards it needs. The full `board.json` (130 KB+) is *never* loaded into context. See [`docs/TOKEN_BUDGET.md`](docs/TOKEN_BUDGET.md) for measurements vs. claude-mem, mem0, and letta.

## The board itself

A live, animated kanban that runs entirely on your machine: cards glide between columns as work moves, plus a **Calendar** view (*"we shipped 17 things on May 25"*) and a **Velocity** view (throughput, cycle time, blockers). Local, private, no sign-in.

## Learn more

- [`docs/KEY_FEATURES.md`](docs/KEY_FEATURES.md) — the full feature tour
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — repo layout, internals, and contributing
- [`CHANGELOG.md`](CHANGELOG.md) — release history

## License

MIT
