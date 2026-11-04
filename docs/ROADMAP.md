# NAYRAASTRA – Roadmap

## Phase 0 — Foundations *(current)*

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

## Phase 1 — Adapter Infrastructure & Scope Guard *(planned)*

**Goal:** First real adapters (Nmap, TShark), Scope Guard, task scheduler.

**Exit criteria:**
- `NmapAdapter` and `TSharkAdapter` parse real tool output into `Observation` rows.
- Scope Guard validates targets against `scope_entries`; out-of-scope tasks are blocked.
- Async task executor respects `max_parallel_tasks` and `rate_limit_per_second`.
- `--dry-run` mode plans but does not execute.
- Integration tests cover a local scan against `127.0.0.1`.

---

## Phase 2 — Workflow Engine & TUI *(planned)*

**Goal:** YAML workflow definitions, DAG scheduler, Prompt Toolkit TUI.

**Exit criteria:**
- Workflow YAML parsed and validated by Pydantic.
- DAG executor resolves dependencies and runs modules in order.
- Prompt Toolkit interactive menu replaces argparse shell.
- Live Rich panels show running tasks and progress.

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

