# NAYRAASTRA UX Guide & Interaction Manual

## 1. Overview
NAYRAASTRA's command-line interface provides a keyboard-driven, numeric-selection interactive shell (inspired by SEToolkit) built on **Prompt Toolkit** (for robust keybindings and input line-editing) and **Rich** (for styled console output and tables).

The CLI is designed for speed, safety, and predictability:
- **Zero mouse dependency**: Every workflow can be executed rapidly using only the keyboard.
- **Fail-safe navigation**: Universal keys (`0`, `Esc`, `Ctrl+C`) ensure the operator is never trapped in a submenu or long-running process.
- **Untrusted data sanitization**: Output from targets, tool executions, and event logs is sanitized through `safe_text()` to prevent terminal escape injection, ANSI styling corruption, or bi-directional override spoofing.

---

## 2. Screen Map (Hierarchy & Flow)

```
                       ┌─────────────────────────┐
                       │     NAYRAASTRA Root     │
                       │     (Main Menu 1..9)    │
                       └────────────┬────────────┘
                                    │
    ┌──────────────┬────────────────┼──────────────┬──────────────┐
    │              │                │              │              │
    ▼              ▼                ▼              ▼              ▼
┌─────────┐  ┌───────────┐   ┌─────────────┐  ┌─────────┐  ┌─────────────┐
│ 1:Recon │  │ 2:Network │   │ 3:Network   │  │ 7:Tasks │  │ 8:Engagement│
│  Menu   │  │   Enum    │   │  Analysis   │  │ & Audit │  │ Management  │
└────┬────┘  └─────┬─────┘   └──────┬──────┘  └────┬────┘  └──────┬──────┘
     │             │                │              │              │
     └─────────────┼────────────────┘              │              ├─► 1: Create Wizard
                   │                               │              ├─► 2: Load Workspace
                   ▼                               │              ├─► 3: View Details
         ┌───────────────────┐                     │              └─► 4: Close Session
         │   RunFlowScreen   │                     │
         ├───────────────────┤                     ├─► [1..N] Task Details
         │ 1. Select Target  │                     └─► [a] Audit Trail & Verifier
         │ 2. Plan Preview   │
         │ 3. Live Execution │
         │ 4. Result Summary │
         └───────────────────┘
```

Other Global Screens:
- `[?]` Global Help Overlay (accessible from any screen, press `0`/`Esc` to return)
- `[9]` Settings & Environment (active configuration, live scope inspection, dry-run toggle, system diagnostics)
- `[4, 5, 6]` Phase Placeholders (Workflows, Findings, Reporting — marked with clean status notices)

---

## 3. Global Keybindings

| Key / Sequence | Scope | Description |
|---|---|---|
| `0` | Any Submenu | Return to previous screen (stack pop) |
| `0` or `q` | Main Menu | Exit NAYRAASTRA (prompts confirmation if tasks active) |
| `Esc` | Universal | Alternative Back key |
| `?` | Universal | Toggle global help overlay |
| `/` | List Screens | Filter / search table rows in-memory |
| `Ctrl+L` | Universal | Clear and redraw current screen |
| `Ctrl+C` | Prompt / Flow | Cancel current prompt or abort running task |

---

## 4. Selection Rules

- **$\le 9$ Items (Single Keypress)**: Menus with 9 or fewer options require only a single digit press (`1`–`9` or `0`). No `Enter` is required, ensuring lightning-fast menu navigation.
- **$> 9$ Items (Enter Confirmation)**: Menus and lists with 10 or more options require typing the full numeric index followed by `Enter` (e.g. `12` + `Enter`).
- **Validated Prompts**: Form fields (e.g. Engagement Wizard, target inputs) allow normal line editing with backspace, arrow keys, and submit on `Enter`. Typing `0` or pressing `Ctrl+C` at any field cancels the wizard/flow.

---

## 5. Status Bar Legend

The persistent bottom status bar displays critical engagement telemetry updated on every refresh:

```
[DEV] | ScanCorp (e2e-1) | Scope: 3 | MAX: active-safe | Tasks: 1R/0Q/0F | Window: active | DRY-RUN
```

- `[DEV]`: Appears when `--dev` or `NAYRAASTRA_DEV=1` is set (using synthetic adapters).
- `Engagement Name`: Active engagement context, or `no engagement` if none is open.
- `Scope: N`: Total count of defined scope rules.
- `MAX: <intrusiveness>`: Active ROE intrusiveness ceiling:
  - `passive` (cyan)
  - `active-safe` (green)
  - `active-intrusive` (yellow)
  - `disruptive` (bold red)
- `Tasks: XR/YQ/ZF`: Live task counters: `R` = Running, `Q` = Queued, `F` = Failed.
- `Window: <state>`: ROE authorized execution window:
  - `active` (green)
  - `expires in Xh` (yellow)
  - `EXPIRED` (bold red)
  - `starts in Xh` (yellow)
  - `indefinite` (dim)
- `DRY-RUN`: Highlighted in yellow when simulation mode is active.

---

## 6. Accessibility & Terminal Compatibility

### Non-TTY Detection
NAYRAASTRA verifies `sys.stdin.isatty()` upon startup. If invoked without an interactive TTY (e.g. redirected from `/dev/null` or piped in CI) and not in dev/subcommand mode, the application prints a clear error and exits with code 1.

### Clean Modes
- `--plain`: Disables Rich boxes, borders, and decorative Unicode symbols, rendering plain ASCII text compatible with screen readers and dumb terminals.
- `--no-color` / `NO_COLOR=1`: Respects the [NO_COLOR](https://no-color.org/) standard, completely disabling ANSI color escape sequences.
