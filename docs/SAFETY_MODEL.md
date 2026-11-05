# NAYRAASTRA – Safety and Authorization Model

This document specifies the safety-critical security architecture of NAYRAASTRA. The framework is designed from the ground up to prevent unintended targets from being scanned, unauthorized tools from being executed, or dangerous parameters from compromising the host or target environments.

---

## 1. Safety Principles

1. **Deny by Default**: Any target not explicitly allowed by an active in-scope rule is strictly forbidden.
2. **Double Opt-In for Disruptive Operations**: Disruptive actions require explicit opt-in in both global application configuration and engagement-specific Rules of Engagement (ROE).
3. **No Shell Execution**: Subprocess execution never uses `shell=True` or constructs command strings. Argument arrays are strictly enforced.
4. **Untrusted Target Strings**: All target inputs from users, configurations, or workflow results are treated as hostile and strictly validated before processing.
5. **Tamper-Evident Accountability**: All authorization checks, denials, task lifecycle transitions, and outputs are hash-chained and logged to an immutable audit log.

---

## 2. Target Normalization and Validation

Before a target is evaluated by the Scope Guard, it must pass strict syntactic and semantic normalization via `normalize_target()`:

| Check | Constraint | Failure Action | Security Rationale |
|---|---|---|---|
| **Empty / Length** | 1 to 253 characters | `ValidationFailure` | RFC 1035 / POSIX length safety |
| **Argument Injection** | Must NOT start with `-` | `ValidationFailure` | Prevents option injection into CLI tools (e.g. `-oX`, `--script`) |
| **Shell Metacharacters** | No `&`, `;`, `\|`, `$`, `>`, `<`, `` ` ``, `\`, `!`, `*`, `?`, `[`, `]`, `(`, `)`, `{`, `}`, `"`, `'`, whitespace, or control characters | `ValidationFailure` | Eliminates command injection risk |
| **IPv4 Octal / Hex / Leading Zeroes** | No `010.0.0.1`, `0x7f.0.0.1`, `127.1` | `ValidationFailure` | Prevents IP parsing bypasses (CVE-2021-29921 class) |
| **IPv4 Short Forms** | Must contain exactly 4 dot-separated octets | `ValidationFailure` | Denies ambiguous decimal notation |
| **IPv6 Zone IDs** | No `%eth0` or `%interface` | `ValidationFailure` | Prevents local zone ambiguity |
| **Strict CIDR** | Strict host-bit check (`strict=True`) | `ValidationFailure` | Rejects non-zero host bits in network prefix |
| **FQDN Labels** | 1–63 chars, alphanumeric + hyphen, no trailing hyphen, no all-numeric TLD | `ValidationFailure` | RFC 1123 / RFC 3696 standard compliance |
| **URL Targets** | Extracted host + port + path in metadata | Validated Host | Normalizes HTTP/HTTPS targets to underlying hosts |

---

## 3. Scope Guard Decision Matrix

The `ScopeGuard` evaluates a normalized `Target` against the set of `ScopeEntry` rules defined for the engagement:

```
                          ┌──────────────────────────┐
                          │   Target Normalization   │
                          └─────────────┬────────────┘
                                        │
                                        ▼
                        ┌───────────────────────────────┐
                        │ Matches ANY Out-of-Scope Rule?│
                        └───────┬───────────────┬───────┘
                                │ Yes           │ No
                                ▼               ▼
                         [ DENY / VETO ] ┌───────────────────────────────┐
                                         │ Matches ANY In-Scope Rule?   │
                                         └───────┬───────────────┬───────┘
                                                 │ Yes           │ No
                                                 ▼               ▼
                                            [ ALLOW ]     [ DENY / VETO ]
```

### Rule Evaluation Hierarchy:
1. **Out-of-Scope Veto**: Any matching `in_scope=False` (deny) rule instantly vetoes authorization, even if a broader in-scope rule encompasses it.
2. **Explicit Coverage**: Target must be explicitly covered by at least one `in_scope=True` (allow) rule.
3. **CIDR Subnetting**: IP addresses are permitted if contained in an in-scope CIDR, provided they are not in an out-of-scope subnet.
4. **Wildcard Subdomains**: `*.example.com` permits `api.example.com` and `sub.corp.example.com`, but excludes the apex `example.com`.
5. **DNS Rebinding Defense**: If a domain resolves to an IP address that falls into an out-of-scope CIDR, it is immediately blocked.

---

## 4. Rules of Engagement (ROE) Gate Checks

The `TaskAuthorizer` validates every task request prior to queueing or execution:

| Check | Condition | Failure Code / Action |
|---|---|---|
| **Engagement Status** | Engagement must be in `active` state | Denied: `Engagement is not active` |
| **Time Window** | Current UTC time must be between `window_start` and `window_end` (if configured) | Denied: `Current time is outside ROE window` |
| **Intrusiveness Ceiling** | Task intrusiveness must NOT exceed engagement `max_intrusiveness` | Denied: `Task intrusiveness exceeds engagement maximum` |
| **Global Safety Ceiling** | Task intrusiveness must NOT exceed global `SafetyConfig.max_intrusiveness` | Denied: `Task intrusiveness exceeds global safety ceiling` |
| **Disruptive Double Opt-In** | `DISRUPTIVE` tasks require `disruptive_enabled=True` in both engagement ROE and global configuration | Denied: `Disruptive tasks require double opt-in` |
| **Capability Filter** | If engagement specifies `allowed_capabilities`, task capability must be present | Denied: `Capability not permitted by ROE` |
| **Scope Guard** | Target must be authorized by `ScopeGuard.check()` | Denied: `Target not covered by in-scope rules` |

All simultaneous violations are aggregated and reported together in the `AuthorizationDecision`.

---

## 5. Intrusiveness Hierarchy

Intrusiveness tiers are strictly ordered:

$$\text{PASSIVE} < \text{ACTIVE\_SAFE} < \text{ACTIVE\_INTRUSIVE} < \text{DISRUPTIVE}$$

1. **PASSIVE**: No packets sent to target; strictly local analysis (e.g. PCAP inspection, local report generation, offline certificate parsing).
2. **ACTIVE_SAFE**: Standard non-disruptive discovery (e.g. ping sweeps, SYN port scans, service version detection). Default maximum ceiling.
3. **ACTIVE_INTRUSIVE**: Intensive probes, heavy fuzzing, or vulnerability testing that may generate significant log volume.
4. **DISRUPTIVE**: Actions with potential for service degradation, state alteration, or denial-of-service. Requires explicit dual opt-in.

---

## 6. Process Runner Security & Sandboxing

All external tool processes are managed through `ProcessRunner`:

- **Executable Resolution**: Binaries must resolve to existing executable files on disk or within the scrubbed `PATH`.
- **Environment Scrubbing**: Environment variables passed to child processes are scrubbed against a strict allowlist (`PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`, `TMPDIR`, `SYSTEMROOT`, `VIRTUAL_ENV`). Secrets, API keys, and internal variables are never leaked.
- **Process Group Isolation**: Processes are spawned in a new session (`start_new_session=True`). On cancellation or timeout, the entire process group is signaled with `SIGTERM`, followed by `SIGKILL` to prevent orphaned background processes.
- **Output Capping**: Standard output and standard error are capped at 50 MB to prevent memory exhaustion from runaway tools.
- **Output Sanitization**: Live emitted task output strips ANSI control characters and carriage returns before publishing to event subscribers.

---

## 7. Tamper-Evident Audit Logging

NAYRAASTRA implements forensic tamper evidence across every engagement:

1. **Engine-Level Immutability**:
   SQLite triggers `audit_log_no_update` and `audit_log_no_delete` reject any `UPDATE` or `DELETE` statements on the `audit_log` table.
2. **Cryptographic Hash Chaining**:
   Every entry computes:
   $$\text{entry\_hash} = \text{SHA-256}\left(\text{canonical\_json}(\text{logged\_at}, \text{event\_type}, \text{actor}, \text{entity\_type}, \text{entity\_id}, \text{payload}, \text{prev\_hash})\right)$$
   where `prev_hash` is the SHA-256 digest of the immediately preceding audit log record (or 64 zeroes for genesis).
3. **Sensitive Key Redaction**:
   All payloads recursively sanitize sensitive keys (`password`, `token`, `secret`, `api_key`, `auth`, `credential`) with `***REDACTED***` and truncate oversized strings before hashing and storage.
4. **Chain Verification**:
   The `verify_chain(entries) -> ChainReport` function verifies cryptographic integrity and flags any modified content, broken links, inserted rows, or truncation.
