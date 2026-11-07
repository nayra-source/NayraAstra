# NAYRAASTRA Manual QA Script

This document provides a comprehensive step-by-step manual testing script for verifying the interactive CLI shell, safety guards, and persistence workflows.

---

## Pre-Requisites
1. Python 3.11+ environment with dependencies installed:
   ```bash
   pip install -e .[dev]
   ```
2. Terminal with 80+ columns width (recommended 100+ columns).

---

## Test Scenario 1: Pre-Flight & Diagnostics

| Step | Action | Expected Outcome |
|---|---|---|
| 1.1 | Run `nayraastra --version` | Outputs `NAYRAASTRA 0.0.1` and exits with code 0. |
| 1.2 | Run `nayraastra doctor` | Displays doctor diagnostics table showing Python version, directories, and tool discovery (Nmap/Fake). |
| 1.3 | Run `nayraastra --plain doctor` | Outputs plain ASCII table without color or unicode box-drawing characters. |
| 1.4 | Run `echo "0" \| nayraastra` | Exits non-zero with error explaining that an interactive TTY is required. |

---

## Test Scenario 2: Main Navigation & Engagement Creation

| Step | Action | Expected Outcome |
|---|---|---|
| 2.1 | Run `nayraastra --dev` | App launches into Main Menu. Bottom toolbar displays `[DEV]` badge and `Engagement: None`. |
| 2.2 | Press `?` | Global help overlay opens showing keybindings and navigation tips. |
| 2.3 | Press `0` or `Esc` | Help overlay closes; returns to Main Menu. |
| 2.4 | Press `2` (Network Enumeration) | Locked warning appears: `"No active engagement. Open or create an engagement first (Option 8)."`. |
| 2.5 | Press `8` (Engagement Management) | Engagement menu opens. Options 3 and 4 show `[locked: no active engagement]`. |
| 2.6 | Press `1` (Create new engagement) | Wizard Step 1 opens. Fill in: Name (`Demo Pentest`), Client (`Acme Corp`), Auth Reference (`AUTH-QA-001`), Start (`now`), End (`+7d`), Intrusiveness (`2` for active-safe). |
| 2.7 | Wizard Step 2 (Scope) | Select `1` (Add target): enter `10.10.0.0/24`, In-Scope `y`, Note `Internal subnet`. Select `1` again: enter `10.10.0.99`, In-Scope `n`, Note `DC Out of scope`. Select `3` (Finish scope). |
| 2.8 | Wizard Step 3 (Review) | Review table shows parameters and 2 scope entries. Enter `y` to confirm. |
| 2.9 | Screen returns to Engagement | Status bar updates: `Demo Pentest`, `Scope: 2`, `MAX: active-safe`. |
| 2.10 | Press `0` | Returns to Main Menu. Header displays `Engagement: Demo Pentest | Scope: 2`. |

---

## Test Scenario 3: Task Execution & Scope Guard Veto

| Step | Action | Expected Outcome |
|---|---|---|
| 3.1 | Press `2` (Network Enumeration) | Enumeration capabilities list opens: `1) TCP / UDP Port Scan`, `2) Service Version Detection`. |
| 3.2 | Press `1` (Port Scan) | In-scope targets list displays `10.10.0.0/24`. Prompt asks for target number or direct value. |
| 3.3 | Type `10.10.0.5` | Plan preview is rendered showing Capability, Target, Fake adapter command, and estimated duration. |
| 3.4 | Type `y` to confirm | Live progress view streams simulated adapter output. Task transitions to `SUCCEEDED`. Results view shows open ports and artifacts. |
| 3.5 | Press `0` twice | Returns to Main Menu. |
| 3.6 | Repeat for out-of-scope target | Press `2` -> `1`, enter `10.10.0.99`, type `y` to confirm. |
| 3.7 | Verification | Safety gate triggers: Task is marked `BLOCKED` with message indicating match with out-of-scope rule `10.10.0.99`. Fake adapter is never executed. |

---

## Test Scenario 4: Audit Trail & Integrity Check

| Step | Action | Expected Outcome |
|---|---|---|
| 4.1 | Press `7` (Tasks & Audit Log) | Tasks history displays both tasks (`SUCCEEDED` and `BLOCKED`). |
| 4.2 | Press `a` (Audit Trail) | Paged audit log displays events with green banner: `✓ HASH-CHAIN VALID: N entries verified (Genesis → Head unbroken)`. |
| 4.3 | Press `/` | Type search term (e.g. `task.blocked`). Table filters in real-time. |
| 4.4 | Press `0` twice | Returns to Main Menu. |

---

## Test Scenario 5: Settings & Workspace Resumption

| Step | Action | Expected Outcome |
|---|---|---|
| 5.1 | Press `9` (Settings & Environment) | Displays active configuration, current scope rules, and environment doctor. |
| 5.2 | Press `d` | Toggles dry-run mode ON. Status bar highlights `DRY-RUN`. |
| 5.3 | Press `0` | Returns to Main Menu. |
| 5.4 | Press `0` then `y` | App exits cleanly with return code 0. |
| 5.5 | Re-launch `nayraastra --dev` | Main Menu opens. Press `8` -> `2` (Load existing engagement). |
| 5.6 | Select `1` (`Demo Pentest`) | Engagement is re-opened. State, scope, and task history are fully restored from disk. |
