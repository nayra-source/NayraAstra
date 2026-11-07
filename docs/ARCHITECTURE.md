# NAYRAASTRA – Architecture

## Overview

NAYRAASTRA is an *orchestration layer* for penetration testing.  It drives
external tools through typed adapters, persists structured results in SQLite,
and assembles findings into auditable reports.  It never implements scanning
logic itself.

---

## Layered Architecture

```
┌─────────────────────────────────────────────────────┐
│  CLI  (argparse / Prompt Toolkit TUI – Phase 2+)    │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│  Runtime Composition Root (src/nayraastra/runtime.py)│
│  wires concrete Repositories, Adapters & Services   │
└───────────┬───────────────────────┬─────────────────┘
            │                       │
┌───────────▼──────────┐  ┌────────▼────────────────┐
│  Modules (Phase 2+)  │  │  Results / Reporting    │
│  (port-scan, vuln …) │  │  (Artifacts, Obs, Jinja)│
└───────────┬──────────┘  └────────┬────────────────┘
            │                       │
┌───────────▼───────────────────────▼─────────────────┐
│  Adapters (ToolAdapter ABC, FakeAdapter, Registry)  │
│  wrap subprocess execution without shell=True       │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│  Core (Domain, Scope Guard, Authorizer, Audit, Bus) │
│  Defines Ports (Protocols) in core/ports.py         │
│  No dependency on other NAYRAASTRA layers!          │
└───────────────────────▲─────────────────────────────┘
                        │ implements ports
┌───────────────────────┴─────────────────────────────┐
│  DB (Sqlite Repositories, Migrator, Triggers)       │
└─────────────────────────────────────────────────────┘
```

**Dependency rule:** `cli → runtime → modules → core/workflow → adapters/results → db`

- `core` defines abstract **ports** (`typing.Protocol`) in `src/nayraastra/core/ports.py`.
- `core` has **no dependency on other NAYRAASTRA layers** (`core` does not import `db`, `cli`, `modules`, `adapters`, or `runtime`).
- `db` implements repository and sink ports.
- `adapters` implements adapter ports and registry.
- `runtime.py` is the single composition root allowed to import all layers.
- Enforced by AST-based test `tests/unit/test_architecture.py`.

---

## Workspace & Database Architecture (ADR-010)

NAYRAASTRA uses **one SQLite database per engagement workspace**:

```
~/.nayraastra/
├── config.yaml              # Optional global config overrides
├── engagements.json         # Atomic index of known engagements
└── workspaces/
    └── <engagement_id>/
        ├── nayraastra.db    # Isolated engagement database (schema v2)
        ├── artifacts/       # Raw tool outputs, PCAPs, dumps
        └── logs/            # Task execution logs
```

Workspaces are completely self-contained and portable: copying or archiving `<engagement_id>/` preserves the complete evidentiary history, tasks, artifacts, and immutable audit logs.

---

## Task Lifecycle State Machine

Tasks progress through a strictly validated state machine:

```
                  ┌───────────────┐
                  │    PENDING    │
                  └──┬───┬─────┬──┘
                     │   │     │
          ┌──────────┘   │     └──────────┐
          │              │                │
          ▼              ▼                ▼
   ┌─────────────┐ ┌───────────┐   ┌─────────────┐
   │   RUNNING   │ │  BLOCKED  │   │  CANCELLED  │
   └──┬───┬───┬──┘ └───────────┘   └─────────────┘
      │   │   │
┌─────┘   │   └─────┐
▼         ▼         ▼
┌───────────┐ ┌───────────┐ ┌───────────┐
│ SUCCEEDED │ │  FAILED   │ │ CANCELLED │
└───────────┘ └───────────┘ └───────────┘
```

- **Allowed transitions**:
  - `pending -> running | blocked | cancelled | skipped`
  - `running -> succeeded | failed | cancelled`
- **Terminal states**: `succeeded`, `failed`, `blocked`, `cancelled`, `skipped` (no outgoing transitions).
- Denied tasks are saved as `BLOCKED` and never dispatched to tool adapters.

---

## Typed Domain Event Bus

In-process typed events published across task lifecycle:

| Event Class | Type String | Description |
|---|---|---|
| `EngagementOpened` | `engagement.opened` | Engagement workspace loaded |
| `TaskQueued` | `task.queued` | Task authorized and placed in queue |
| `TaskStarted` | `task.started` | Task execution started |
| `TaskOutput` | `task.output` | Live stdout/stderr line (sanitized) |
| `TaskSucceeded` | `task.succeeded` | Task completed with exit code 0 |
| `TaskFailed` | `task.failed` | Task execution failed or crashed |
| `TaskBlocked` | `task.blocked` | Policy/Scope violation blocked task |
| `ScopeViolation` | `scope.violation` | Scope breach attempt detected |
| `ToolMissing` | `tool.missing` | Required external tool not found |

---

## Interactive CLI Shell Architecture (Phase 2, ADR-015–018)

NAYRAASTRA's interactive shell (`nayraastra.cli`) is a thin, keyboard-driven navigation layer over `Runtime`:

```
┌─────────────────────────────────────────────────────────────┐
│                       App Event Loop                        │
│                 (asyncio / InputDriver)                     │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
┌──────────────▼──────────────┐ ┌─────────────▼───────────────┐
│     Navigator (Stack LIFO)  │ │      Prompt Toolkit         │
│   Screen Transitions        │ │   Keybindings / Toolbar     │
│   [Push, Pop, Replace, Stay]│ │   (Single-key <=9, Enter >9)│
└──────────────┬──────────────┘ └─────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│                    Interactive Screens                      │
│   - MainMenuScreen                                          │
│   - EngagementScreen & EngagementWizardScreen               │
│   - ModuleMenuScreen (Capabilities with locking badges)     │
│   - RunFlowScreen (Target, Plan preview, Live output, Done) │
│   - TasksScreen & AuditScreen (Verification badge & search) │
│   - SettingsScreen (Config, Live scope edit, Doctor)        │
│   - HelpScreen (Global ? overlay)                           │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│                      Rich Rendering                         │
│   - safe_text() sanitization (strips ANSI, NUL, escapes)    │
│   - Breadcrumbs, Semantic Status Bar, Tables, Live Panels   │
└─────────────────────────────────────────────────────────────┘
```

**Architecture Constraints:**
- **Zero Business Logic in CLI**: The CLI is purely presentational and dispatches all operations to `Runtime` and public domain models.
- **Strict AST Layer Enforcement**: `tests/unit/test_architecture.py` asserts that `cli` never imports from `nayraastra.db`, `nayraastra.adapters`, or calls `subprocess`.
- **String Sanitization**: Every string from targets, tool output, or engagements is sanitized with `safe_text()` before Rich rendering.

---

## Safety Model

See [SAFETY_MODEL.md](file:///Users/aryan/Documents/NayraAstra/docs/SAFETY_MODEL.md) for full specifications of Scope Guard CIDR containment, ROE boundary checks, intrusiveness ceilings, argument injection defenses, and tamper-evident audit chaining.

---

## Design Principles

1. **Adapters, not scripts** – external tools are invoked via argument lists only.
2. **Pydantic at every boundary** – all external data (config, tool output, user input) is validated.
3. **No shell=True, ever** – eliminates shell-injection by construction.
4. **Explicit over implicit** – Context is passed explicitly, never via globals.
5. **Idempotent operations** – migrations, logging setup, and directory creation are all safe to repeat.
6. **Audit trail** – the `audit_log` table is immutable by design (SQL triggers).

---

> *Items marked **planned** are part of Phase 1 or later.*
