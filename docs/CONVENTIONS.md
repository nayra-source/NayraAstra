# NAYRAASTRA – Coding Conventions

## Typing

- All functions and methods must have complete type annotations (parameters and return type).
- Use `from __future__ import annotations` at the top of every module.
- Never use `Any` unless wrapping truly dynamic data at a package boundary; document the reason.
- Use `TypeAlias` for complex reused types.

## Subprocess / Shell

- **Never** use `shell=True` with `subprocess`.  Pass argument lists only.
- **Never** interpolate user-supplied strings into argument lists without validation.
- **Never** use `os.system`, `os.popen`, or any shell-invoking helper.

## Configuration and Input Validation

- All external data (config files, CLI args, tool output) must be parsed through a Pydantic v2 model.
- Use `extra="forbid"` on all root config models.
- Use `yaml.safe_load` only — never `yaml.load`.
- Validate engagement ids and file paths before use (see `core/paths.py`).

## Error Handling

- Raise `NayraastraError` subclasses across package boundaries (never raw `sqlite3.Error`, etc.).
- Never swallow exceptions silently; log at `WARNING` or above, then re-raise or convert.
- Use `details={}` to attach structured context for debugging.

## Logging

- Use `logging.getLogger("nayraastra.<module>")` — never the root logger.
- Never log raw tool output at a level above `DEBUG` without sanitising with `ControlCharFilter`.
- Do not use `print()` in library code; use `rich.console.Console` only in CLI.

## Naming

- Modules: `snake_case`. Classes: `PascalCase`. Constants: `SCREAMING_SNAKE_CASE`.
- Error codes: `SCREAMING_SNAKE_CASE` stable strings on `default_code`.
- Database columns: `snake_case`. SQL keywords: `UPPER CASE`.
- Migration files: `NNNN_short_description.sql` (zero-padded 4-digit version).

## Imports and Layers

- Respect the dependency rule: `cli → modules → core/workflow → adapters/results → db`.
- Lower layers **must not** import from upper layers.
- Use local imports inside functions only to break genuine circular dependencies; document why.

## Tests

- Every test file uses `pytest.mark.unit` or `pytest.mark.integration`.
- Tests must use `tmp_path` and `monkeypatch` to avoid touching real home dirs, networks, or system state.
- No test may call a real external binary (Nmap, etc.) without being in `tests/integration/`.
- Aim for ≥ 80 % line coverage on `core/` and `db/`.
- Fixture scope: prefer `function` scope for filesystem fixtures to avoid state leakage.

## Commits

Follow **Conventional Commits**:

```
<type>(<scope>): <short summary>

Types: feat, fix, chore, docs, test, ci, refactor, style, perf
```

Examples:
- `feat(db): add migrator with checksum verification`
- `test(core): add engagement id validation edge cases`
- `ci: add GitHub Actions matrix for 3.11 and 3.12`

---

## AI-Assistant Rules

These rules apply to AI coding assistants (GitHub Copilot, Claude, etc.) working on this codebase:

1. **One task per session** – do not combine unrelated changes in a single PR.
2. **Never invent tool flags** – verify every CLI flag for Nmap, TShark, etc. against the man page or official docs before writing it into an adapter.
3. **Never modify base contracts without an ADR** – changing `NayraastraError`, `AppConfig`, the migration format, or the DB schema requires a new ADR in `docs/DECISIONS.md`.
4. **Always run `make check` before finishing** – do not submit code that fails lint, type-check, or tests.
5. **Placeholders stay empty** – Phase 1+ placeholder packages must remain empty (docstring only) until the phase begins.
6. **No shell=True, ever** – this is non-negotiable.
7. **Cite your sources** – if adding a new dependency or technique, record the rationale in `DECISIONS.md` or a code comment.

