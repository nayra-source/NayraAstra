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
│  Modules  (port-scan, vuln-enum, brute-force …)     │
│           compose Adapters into operations           │
└───────────┬───────────────────────┬─────────────────┘
            │                       │
┌───────────▼──────────┐  ┌────────▼────────────────┐
│  Workflow Engine      │  │  Results / Reporting     │
│  (scheduler, DAG,     │  │  (ToolResult models,     │
│   Scope Guard)        │  │   Jinja2 templates)      │
└───────────┬───────────┘  └────────┬────────────────┘
            │                       │
┌───────────▼───────────────────────▼─────────────────┐
│  Adapters  (Nmap, TShark, Bettercap, hping3 …)      │
│            wrap subprocess, never shell=True         │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│  Core  (config, logging, paths, errors)             │
│  DB    (sqlite3, migrator, versioned SQL)            │
└─────────────────────────────────────────────────────┘
```

**Dependency rule:** `cli → modules → core/workflow → adapters/results → db`

Lower layers **never** import upper layers.  `core` must not import from `db`,
`cli`, or `modules`.

---

## Domain Concepts

| Concept | Description |
|---|---|
| **Engagement** | A named, scoped penetration test.  All data belongs to exactly one engagement. |
| **Target** | An in-scope host or network range (stored as `scope_entries`). |
| **Task** | A single adapter invocation with arguments, status, and exit code. |
| **Adapter** | A thin wrapper around one external tool binary (Phase 1+). |
| **Artifact** | A raw output file (PCAP, XML, text) produced by a task. |
| **Observation** | A structured datum extracted from an artifact (open port, banner). |
| **Finding** | A security issue with severity, confidence, and evidence links. |
| **Workflow** | A YAML-defined DAG of modules and their dependencies (Phase 1+). |
| **Context** | The runtime object carrying engagement id, config, and DB connection. |

---

## Request Flow

```
User invokes CLI command
  → CLI parses arguments, loads AppConfig, opens DB connection
  → Creates EngagementContext
  → Workflow engine resolves DAG (Phase 1+)
  → Scope Guard validates each target (Phase 1+)
  → Module is dispatched
    → Adapter builds subprocess argv list (no shell=True)
    → Adapter streams stdout/stderr to raw Artifact
    → Parser extracts Observations from raw output
  → Observations are persisted to DB
  → Findings are correlated and stored
  → Report is rendered from Jinja2 template (Phase 2+)
```

---

## Safety Model *(Scope Guard – planned Phase 1)*

**Intrusiveness tiers** (ascending risk):

| Tier | Description |
|---|---|
| `passive` | Read-only, no packets sent (DNS lookups, OSINT) |
| `active-safe` | Light probing, standard nmap SYN scan |
| `active-intrusive` | Aggressive scanning, banner grabbing |
| `disruptive` | DoS-adjacent, exploit payloads — requires explicit opt-in |

**Controls:**

- `SafetyConfig.max_intrusiveness` caps the tier globally.
- `disruptive_enabled = false` (default) hard-blocks disruptive tasks.
- Every task is checked against in-scope targets before execution.
- All task dispatches are written to `audit_log` (append-only triggers).
- `--dry-run` mode plans but does not execute (Phase 1+).

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
