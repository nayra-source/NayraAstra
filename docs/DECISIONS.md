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

---

## ADR-009: Layering, Ports, and Composition Root

**Date:** 2026-11-05
**Status:** Accepted

### Context
Phase 1 introduces complex cross-cutting concerns: persistence, execution, adapters, auditing, and scope enforcement. Without strict boundaries, circular dependencies and tight coupling to SQLite or specific tool runners could easily degrade maintainability.

### Decision
`core` defines abstract **ports** (`typing.Protocol`) in `src/nayraastra/core/ports.py` for all persistence repositories, audit sinks, workspace providers, tool adapters, and registries.
- `core` never imports `db`, `cli`, `modules`, `adapters`, or `runtime`.
- Concrete implementations are located in `src/nayraastra/db/` and `src/nayraastra/adapters/`.
- A single composition root `src/nayraastra/runtime.py` wires concrete dependencies together and exposes a high-level `Runtime` facade.
- Enforced automatically by AST-based test `tests/unit/test_architecture.py`.

---

## ADR-010: One SQLite Database per Engagement Workspace

**Date:** 2026-11-05
**Status:** Accepted

### Context
Pentesting engagements require strict evidentiary containment, workspace portability (e.g. archiving or transmitting an engagement as a tarball), and operational safety against accidental cross-engagement contamination.

### Decision
Each engagement has its own isolated directory `<home>/workspaces/<engagement_id>/` containing:
- `nayraastra.db` (self-contained SQLite database with engagement, scope, tasks, findings, evidence, artifacts, and audit log)
- `artifacts/` (directory for tool outputs, pcaps, and evidentiary data)
- `logs/` (directory for execution logs)

A global index `<home>/engagements.json` is updated atomically using tempfiles and atomic file replace (`os.replace`) to index known engagements.

---

## ADR-011: Tamper-Evident Hash-Chained Audit Log

**Date:** 2026-11-05
**Status:** Accepted

### Context
Forensic, compliance, and legal standards require that all operations within an engagement have verifiable integrity. If an attacker modifies or deletes entries directly in SQLite, the system must detect it.

### Decision
1. Immutability triggers: SQLite `BEFORE UPDATE` and `BEFORE DELETE` triggers abort any mutation on `audit_log`.
2. SHA-256 hash chaining: Each entry records `prev_hash` (the previous entry's `entry_hash` or a 64-zero genesis hash) and `entry_hash` computed over canonical JSON representation of `(logged_at, event_type, actor, entity_type, entity_id, payload, prev_hash)`.
3. Offline verifier: `verify_chain(entries) -> ChainReport` detects tampering, reordering, insertion, or truncation.

---

## ADR-012: Sequential Async Scheduler with Rate Limiting

**Date:** 2026-11-05
**Status:** Accepted

### Context
Phase 1 focuses on core execution correctness and safety. Parallel execution of pentesting tools before robust workflow dependency modeling and resource governance is unsafe.

### Decision
Scheduler executes tasks strictly sequentially (concurrency clamped to 1 in Phase 1).
- Uses `asyncio` for non-blocking process supervision.
- Implements a token bucket rate limiter (`AsyncRateLimiter`) to obey global rate limits.
- Supports dry-run execution without invoking external tool adapters.
- Interrupted or abandoned tasks in `RUNNING` status are recovered upon startup.

---

## ADR-013: Injectable Clock and IdGenerator Protocols

**Date:** 2026-11-05
**Status:** Accepted

### Context
Direct calls to `datetime.now()` and `uuid.uuid4()` lead to non-deterministic tests, flakiness, and difficulties verifying time-window boundaries in Rules of Engagement.

### Decision
Define `@runtime_checkable` protocols `Clock` and `IdGenerator` in `src/nayraastra/core/domain/time_id.py`.
- Production uses `UtcClock` (always timezone-aware UTC) and `UuidGenerator`.
- Testing uses `FrozenClock` (advanceable) and `StaticIdGenerator` / `SequenceIdGenerator`.
- Domain services and repositories require injected clock/ID instances.

---

## ADR-014: Hypothesis Dev Dependency for Scope Matching Property Tests

**Date:** 2026-11-05
**Status:** Accepted

### Context
Scope Guard CIDR containment, IP normalization, and wildcard domain matching are security-critical boundaries where edge cases (such as zero-padding, CIDR overlaps, apex domains) could cause serious accidental scanning of out-of-scope targets.

### Decision
Include `hypothesis` in optional `dev` dependencies. Use property-based testing in `tests/unit/test_scope.py` to assert idempotency, CIDR invariants, and invalid IP boundary rejection across thousands of randomized inputs. Zero runtime dependencies are added.

---

## ADR-015: Prompt Toolkit for Input, Rich for Output (No Textual Framework)

**Date:** 2026-11-07
**Status:** Accepted

### Context
Phase 2 builds the interactive terminal shell. Options considered:
1. Textual: heavy async TUI framework, widget-driven, complex state management, mouse-centric paradigms, and heavy runtime footprint.
2. Curses / Urwid: low-level, awkward cross-platform terminal handling.
3. Prompt Toolkit + Rich: already approved runtime dependencies in `pyproject.toml`.

### Decision
Use `prompt_toolkit` exclusively for keybindings, numeric choice listening, text line editing, and bottom toolbar rendering. Use `rich` exclusively for styled console rendering, tables, panels, breadcrumbs, and live progress bars. Textual is explicitly excluded.

### Consequences
Zero new runtime dependencies. Full control over the terminal lifecycle and layout. Clean testability via `ScriptedInputDriver`.

---

## ADR-016: View-Model / Renderer Split and Untrusted String Sanitization

**Date:** 2026-11-07
**Status:** Accepted

### Context
The CLI renders data originating from untrusted sources (target names, raw tool outputs, command arguments, engagement notes). Rendering raw strings via Rich or printing them directly could trigger unintended terminal formatting (Rich markup injection), ANSI escape code injection, cursor manipulation, or directional character spoofing (bidi overrides).

### Decision
1. Separation of Concerns: Views compute pure data `ViewModel` structures, and renderers convert view-models into Rich renderables.
2. Central Sanitizer: Implement `safe_text(raw, allow_newlines=False)` in `nayraastra.cli.rendering`. It strips ANSI escape sequences, strips ASCII control characters (preserving newline/tab only when requested), removes Unicode bidi directional overrides, and escapes Rich markup via `rich.markup.escape`. Every string from targets, tool output, or engagement fields must pass through `safe_text()`.

### Consequences
Prevents terminal injection attacks and rendering corruption. Enforced by unit tests in `tests/unit/test_cli_safe_text.py`.

---

## ADR-017: Interactive Event Loop Ownership and Synchronous CLI Bridge

**Date:** 2026-11-07
**Status:** Accepted

### Context
The underlying `Runtime` services and adapters rely on `asyncio` (e.g. for scheduler execution, rate limiting, and process timeouts). The CLI entrypoint `nayraastra` is invoked synchronously by console scripts.

### Decision
The top-level `App` class exposes an `async def run_async() -> int` loop managing the screen stack and Prompt Toolkit drivers, and a synchronous `def run() -> int` method that initializes and runs the `asyncio` event loop via `asyncio.run()`. Subcommands (`doctor`, `init-db`, `--version`) execute synchronously without starting the interactive loop.

---

## ADR-018: Single-Key Immediate Selection ($\le 9$ items) vs. Enter Confirmation ($> 9$ items)

**Date:** 2026-11-07
**Status:** Accepted

### Context
A core goal of SEToolkit-style keyboard navigation is fast, ergonomic interaction without requiring the operator to hit `Enter` after every single menu selection, while simultaneously supporting menus/lists that exceed 9 items.

### Decision
Implement numeric selection rules based on item count:
1. For screens with $\le 9$ items, single digit keypresses (`1`–`9`, `0`) are captured immediately by Prompt Toolkit keybindings without requiring `Enter`.
2. For screens or lists with $> 9$ items (such as large engagement lists or long task histories), input mode switches to multi-digit entry requiring `Enter` confirmation.
3. Invalid inputs display an inline hint without crashing or resetting the screen stack.
