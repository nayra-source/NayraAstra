# NAYRAASTRA – Decision Log (ADRs)

Architectural Decision Records are numbered sequentially.  Once merged, a
decision's number and title are immutable.  Superseded decisions are marked
but kept for history.

---

## ADR-001: Python 3.11+ and `src/` layout

**Date:** 2026-11-04
**Status:** Accepted

### Context
Need a minimum Python version and a package layout that avoids import-path
confusion during development.

### Decision
Require Python ≥ 3.11 for `tomllib` stdlib support, improved error messages,
`typing.Self`, and `StrEnum`.  Use a `src/` layout so the installed package is
always imported (never the source tree directly), which catches packaging bugs
early.

### Consequences
CI matrix must include 3.11 and 3.12.  Local development requires explicit
`pip install -e .`.

---

## ADR-002: Plain `sqlite3` with versioned SQL migrations

**Date:** 2026-11-04
**Status:** Accepted

### Context
Need a persistence layer.  Options: SQLAlchemy ORM, SQLAlchemy Core, raw
`sqlite3`, or an external migration tool (Alembic, Flyway).

### Decision
Use Python stdlib `sqlite3` with hand-written SQL migration files
(`NNNN_name.sql`).  A lightweight custom migrator applies them in order,
verifies SHA-256 checksums, and stores applied versions in `schema_version`.

### Rationale
- Zero additional dependencies for the core DB layer.
- SQL migrations are readable, reviewable, and portable.
- Full control over `PRAGMA` settings (WAL, FK enforcement).
- Checksum verification prevents silent schema drift.

### When to revisit
If concurrent write throughput becomes a bottleneck, consider PostgreSQL +
SQLAlchemy Core.  Document in a new ADR before migrating.

---

## ADR-003: `hatchling` as build backend

**Date:** 2026-11-04
**Status:** Accepted

### Context
Need a PEP 517/518-compliant build backend for `pyproject.toml`.

### Decision
Use `hatchling`.  It supports dynamic version from source (`__version__`),
is actively maintained, and requires no `setup.py`.

### Alternatives considered
`setuptools` (more complex config), `flit` (limited for future needs), `poetry`
(opinionated lock-file model not needed here).

---

## ADR-004: `argparse` for Phase 0 entry point; Prompt Toolkit reserved for Phase 2

**Date:** 2026-11-04
**Status:** Accepted

### Context
Phase 0 needs a minimal CLI.  The full TUI (interactive menus, live output
panels) is out of scope until Phase 2.

### Decision
Use stdlib `argparse` for the Phase 0 CLI (`--version`, `doctor`, `init-db`).
`prompt_toolkit` is listed as a runtime dependency so it installs, but no TUI
code is written yet.  Phase 2 will replace the argparse shell with a full Prompt
Toolkit application.

### Consequences
The `cli/__init__.py` module must remain minimal.  Do not add menus, interactive
prompts, or Prompt Toolkit widgets in Phase 0 or 1.

---

## ADR-005: `yaml.safe_load` only

**Date:** 2026-11-04
**Status:** Accepted

### Context
PyYAML's `yaml.load` can deserialise arbitrary Python objects, creating a
remote-code-execution risk if untrusted YAML is ever loaded.

### Decision
Use only `yaml.safe_load` throughout the codebase.  `yaml.load` is banned.
Enforced by `ruff` rule `S506` and `grep` in the acceptance checklist.

---

## ADR-006: Synchronous I/O for Phase 0; async scheduler planned for Phase 1

**Date:** 2026-11-04
**Status:** Accepted

### Context
Phase 0 has no concurrent task execution.  Async I/O would add complexity
without benefit at this stage.

### Decision
All Phase 0 code is synchronous.  The workflow engine (Phase 1) will introduce
`asyncio` for concurrent adapter invocations.  The `ExecutionConfig` model
already carries `max_parallel_tasks` and `rate_limit_per_second` to avoid
retrofitting the config schema.

### Consequences
No `async def` in Phase 0.  When Phase 1 begins, open a new ADR covering the
async executor design.

---

## ADR-007: Coverage threshold set to 70% globally (80% goal for core/db)

**Date:** 2026-11-04
**Status:** Accepted

### Context
The prompt specifies ≥ 80% coverage on `core` and `db`.  Setting a single
global `fail_under = 80` would fail due to placeholder packages (adapters,
modules, etc.) which are intentionally empty docstrings.

### Decision
Set global `fail_under = 70` in `pyproject.toml` to avoid false failures from
empty placeholder packages.  The acceptance checklist independently verifies
that `core/` and `db/` individually exceed 80%.

---

## ADR-008: `audit_log` immutability via SQL triggers

**Date:** 2026-11-04
**Status:** Accepted

### Context
The audit log must be append-only to maintain evidentiary integrity.

### Decision
Use `BEFORE UPDATE` and `BEFORE DELETE` triggers on `audit_log` that call
`RAISE(ABORT, '...')`.  This is enforced at the database engine level regardless
of application code paths.

### Alternatives considered
Application-level enforcement only (insufficient; can be bypassed by direct DB
access).  Row-level security (not available in SQLite).

