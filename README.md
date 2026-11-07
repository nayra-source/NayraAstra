# NAYRAASTRA

> **A pentesting automation and orchestration framework — not a tool menu.**

NAYRAASTRA orchestrates external security tools (Nmap, TShark, Bettercap, etc.)
through typed adapters, stores structured results in SQLite, and generates
auditable reports.  It is an *orchestration layer*: it never implements scanning
logic itself.

---

## Status: Phase 2 — Interactive CLI Shell

Phase 2 is complete. The keyboard-driven interactive CLI shell is operational:
- **SEToolkit-Style Numeric Navigation**: Single-key selection for $\le 9$ items, multi-digit entry with `Enter` for $> 9$ items, universal `0`/`Esc` Back, and persistent breadcrumbs.
- **Persistent Telemetry Status Bar**: Real-time status bar showing active engagement, defined scope count, ROE intrusiveness ceiling, dry-run mode, task counters, and time-window state.
- **Untrusted String Sanitization**: Central `safe_text()` sanitizer stripping ANSI escape sequences, control characters, bidi overrides, and escaping Rich markup.
- **Complete Screen Stack**: Interactive Engagement Wizard, Category capability menus with locked indicators, Run Flow (Target selection, Scope Guard pre-check, Plan preview, streaming Live execution, and Result view), Tasks & Audit Log with tamper-evident chain verification badge, and Settings/Diagnostics.
- **Strict Layer Isolation**: `cli` contains zero business logic and imports only `Runtime` and public domain models (never `db`, `adapters`, or `subprocess`), enforced by AST tests.
- **Comprehensive Docs & QA**: Full UX Guide (`docs/UX_GUIDE.md`) and step-by-step Manual QA Script (`docs/MANUAL_QA.md`).

See [`docs/ROADMAP.md`](docs/ROADMAP.md), [`docs/UX_GUIDE.md`](docs/UX_GUIDE.md), and [`docs/SAFETY_MODEL.md`](docs/SAFETY_MODEL.md).

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
  runtime.py   # Composition root and Runtime/Session facade
  core/        # Domain models, scope guard, authorizer, audit, events, scheduler (no dependency on other layers)
  db/          # Connection, migrator, SQL migrations, repository implementations
  adapters/    # ToolAdapter ABC, registry, process runner, fake adapters
  cli/         # CLI entry point (argparse doctor, init-db, version)
  modules/     # Phase 2+ placeholder
  workflow/    # Phase 2+ placeholder
  context/     # Phase 2+ placeholder
  results/     # Phase 2+ placeholder
  reporting/   # Phase 2+ placeholder
config/        # default.yaml, profiles/, rules/, workflows/
docs/          # architecture, safety model, conventions, decisions, roadmap
tests/         # unit/ integration/ fixtures/
```

## Documentation

| Document | Description |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layered architecture, domain model, ports, composition root |
| [`docs/SAFETY_MODEL.md`](docs/SAFETY_MODEL.md) | Scope Guard rules table, ROE checks, audit chain, process safety |
| [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) | Coding and AI-assistant rules |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | ADR log (ADR-001 through ADR-014) |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phase roadmap with exit criteria |
