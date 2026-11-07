# NAYRAASTRA – Roadmap

## Phase 0 — Foundations *(completed)*

**Goal:** Project skeleton, core infrastructure, database layer, minimal CLI.

**Exit criteria:**
- `make check` passes (ruff, mypy strict, pytest green, ≥ 80% core/db coverage).
- `nayraastra doctor` and `nayraastra init-db` work.
- No `shell=True`, no `yaml.load`, no hardcoded paths.
- All 10 schema tables created by migration; audit_log immutability enforced.
- Pre-commit hooks pass on all files.
- CI workflow valid and mirrors `make check`.
- Conventional commit history.

---

## Phase 1 — Core Skeleton & Safety Spine *(completed)*

**Goal:** Safety-critical engine core: engagements, scope enforcement, audit chaining, adapter contracts, task state machine, sequential scheduler, event bus, and runtime composition root proven with fake adapters.

**Exit criteria:**
- [x] Pure Pydantic v2 domain models (`core/domain/`) with injectable `Clock` and `IdGenerator`.
- [x] Strict target normalization and Scope Guard (`core/scope/`) rejecting argument injection (`-` prefix), CIDR containment, wildcard subdomains, and DNS rebinding.
- [x] Task Authorizer gate enforcing ROE window, intrusiveness ceilings, disruptive double opt-in, and capability filters.
- [x] Tamper-evident hash-chained audit logging (`prev_hash`, `entry_hash`, SHA-256) with trigger-based SQL immutability and offline chain verification.
- [x] One SQLite DB per engagement workspace (`workspaces/<id>/nayraastra.db`) and atomic global index (`engagements.json`).
- [x] Async process runner (`shell=False`, argument lists only, process group kill on cancel/timeout, env allowlisting).
- [x] Synthetic deterministic fake adapters (`FakeAdapter`, `FakeDisruptiveAdapter`) with test control switches.
- [x] Sequential async scheduler with rate limiting (token bucket) and dry-run execution.
- [x] In-process typed domain event bus (`core/events/`) with subscriber fault isolation and output sanitization.
- [x] Layering and composition root (`runtime.py`) verified by AST architecture tests.
- [x] End-to-end integration test (`tests/integration/test_phase1_e2e.py`) validating the complete lifecycle.
- [x] All 189 tests passing, 85.6% test coverage, strict mypy green, ruff format/lint clean.

---

## Phase 2 — CLI Interactive Shell *(completed)*

**Goal:** Keyboard-driven interactive CLI (SEToolkit-style numeric navigation) built as a thin shell over `Runtime` using Prompt Toolkit and Rich.

**Exit criteria:**
- [x] Keyboard-only interactive navigation with universal controls (`0`/`Esc` Back, `?` Help, `/` Filter, `Ctrl+L` Redraw, `Ctrl+C` Cancel, `q` Quit).
- [x] Numeric selection rules: single keypress for $\le 9$ items, multi-digit with `Enter` for $> 9$ items.
- [x] Persistent Prompt Toolkit status bar displaying engagement name, scope count, ROE intrusiveness ceiling, dry-run mode, live task counters, and time-window state.
- [x] Untrusted string sanitization with central `safe_text()` (strips ANSI, control chars, bidi overrides, escapes Rich markup).
- [x] Full screen stack: Main Menu, Engagement Wizard, Category Menus (Recon, Enumeration, Analysis), Run Flow (Target, Plan preview, Live output streaming via Event Bus, Result view), Tasks & Audit Log with tamper-evident chain verification badge, Settings & Environment.
- [x] AST architecture verification ensuring `cli` never imports `db`, `adapters`, or `subprocess`.
- [x] Full two-session E2E integration test (`tests/integration/test_phase2_cli_e2e.py`) validating engagement creation, scope gating, task execution, audit trail, workspace persistence, and reload.
- [x] UX Guide (`docs/UX_GUIDE.md`) and Manual QA script (`docs/MANUAL_QA.md`).
- [x] All 251 tests passing, strict mypy green, ruff format/lint clean.

---

## Phase 3 — Real Tool Adapters & Workflow Engine *(next)*

**Goal:** First real tool adapters (Nmap, TShark), YAML workflow DAG engine, parallel scheduling, and Prompt Toolkit TUI.

**Exit criteria:**
- `NmapAdapter` and `TSharkAdapter` wrap tools via subprocess without `shell=True` and parse outputs into `Observation` records.
- YAML workflow definitions parsed into DAG and executed by workflow engine.
- Scheduler concurrency unconstrained from Phase 1 sequential clamp to configurable `max_parallel_tasks`.
- Prompt Toolkit interactive TUI with Rich live progress panels.

---

## Phase 3 — Findings & Reporting *(planned)*

**Goal:** Automated finding correlation, Jinja2 report templates.

**Exit criteria:**
- Observations are correlated into `findings` by configurable rules.
- HTML and Markdown reports generated from Jinja2 templates.
- `nayraastra report generate --format html` works end-to-end.

---

## Phase 4 — Extended Adapters *(planned)*

**Goal:** Bettercap, hping3, Gobuster, ffuf adapters.

**Exit criteria:**
- Each adapter has unit tests with fixture output files.
- Intrusiveness tier correctly enforced per adapter.

---

## Phase 5 — Engagement Management TUI *(planned)*

**Goal:** Full engagement lifecycle (create, pause, resume, archive) via TUI.

**Exit criteria:**
- `nayraastra engage new <id>` creates a workspace and DB row.
- Engagement status transitions are audited.

---

## Phase 6 — Plugin / Module SDK *(planned)*

**Goal:** Third-party modules loadable from `~/.nayraastra/plugins/`.

**Exit criteria:**
- Plugin discovery, validation, and sandboxed invocation.
- SDK documentation and example plugin.

---

## Phase 7 — Remote / Distributed Agents *(planned)*

**Goal:** Dispatch tasks to remote NAYRAASTRA agents over gRPC.

**Exit criteria:**
- Agent registers with coordinator; coordinator assigns tasks.
- Results collected back to central DB.

---

## Phase 8 — AI-Assisted Analysis *(planned)*

**Goal:** LLM-assisted finding prioritisation and remediation suggestions.

**Exit criteria:**
- Findings enriched with AI-generated summaries (opt-in, local model).
- No finding data leaves the local machine without explicit user consent.

---

## Phase 9 — Production Hardening & v1.0 *(planned)*

**Goal:** Performance, security audit, documentation, stable public API.

**Exit criteria:**
- All public APIs documented with docstrings and type stubs.
- Security audit completed; no critical findings outstanding.
- `v1.0.0` tag released with full changelog.
