# NAYRAASTRA

> **A pentesting automation and orchestration framework — not a tool menu.**

NAYRAASTRA orchestrates external security tools (Nmap, TShark, Bettercap, etc.)
through typed adapters, stores structured results in SQLite, and generates
auditable reports.  It is an *orchestration layer*: it never implements scanning
logic itself.

---

## Status: Phase 0 — Foundations

The project skeleton, core infrastructure, and database layer are in place.
No scanning adapters, workflow engine, or interactive TUI exist yet.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for planned phases.

---

## ⚠️ Legal and Ethical Use Notice

**NAYRAASTRA must only be used against systems you own or have explicit written
permission to test.**  Unauthorised use of penetration-testing tools is illegal
in most jurisdictions and may result in criminal prosecution.  The authors
accept no liability for misuse.  By using this software you agree that you bear
full responsibility for ensuring your use is lawful and authorised.

---

## Install (development)

```bash
git clone <repo>
cd NayraAstra
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Requires **Python 3.11+**.

## Quick start

```bash
# Check your environment
nayraastra doctor

# Initialise the database (default: ~/.nayraastra/nayraastra.db)
nayraastra init-db

# Initialise a custom database
nayraastra init-db --path /tmp/test.db

# Print version
nayraastra --version

# Same via module invocation
python -m nayraastra --version
```

## Developer commands

```bash
make install    # pip install -e .[dev]
make lint       # ruff check
make format     # ruff format + ruff check --fix
make typecheck  # mypy strict
make test       # pytest with coverage
make check      # all of the above (CI equivalent)
make clean      # remove caches and build artefacts
```

## Project layout

```
src/nayraastra/
  core/        # errors, paths, config, logging  (no external imports)
  db/          # connection, migrator, SQL migrations
  cli/         # entry point (argparse, Phase 0 only)
  adapters/    # Phase 1+ placeholder
  modules/     # Phase 1+ placeholder
  workflow/    # Phase 1+ placeholder
  context/     # Phase 1+ placeholder
  results/     # Phase 1+ placeholder
  reporting/   # Phase 1+ placeholder
config/        # default.yaml, profiles/, rules/, workflows/
docs/          # architecture, conventions, decisions, roadmap
tests/         # unit/ integration/ fixtures/
```

## Documentation

| Document | Description |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layered architecture, domain model, safety design |
| [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) | Coding and AI-assistant rules |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | ADR log |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phase roadmap with exit criteria |

