"""AST-based architectural conformance test.

Enforces layer isolation and dependency direction rules:
- `core` must never import from `db`, `cli`, `modules`, `adapters`, or `runtime`.
- `db` must never import from `cli`, `runtime`, `modules`, or `adapters`.
- `adapters` must never import from `cli`, `runtime`, or `modules`.
- Only `runtime.py` is permitted to compose across all subsystems.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import nayraastra

_PACKAGE_ROOT = Path(nayraastra.__file__).parent


def _get_imports(file_path: Path) -> list[str]:
    """Parse a Python source file with AST and return all nayraastra.* import targets."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("nayraastra"):
                    imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("nayraastra"):
                imports.append(node.module)
            elif node.level and node.level > 0:
                # Relative import
                # Calculate module path based on relative level
                parts = file_path.relative_to(_PACKAGE_ROOT.parent).parts[:-1]
                if node.level <= len(parts):
                    base_pkg = ".".join(parts[: len(parts) - node.level + 1])
                    mod = f"{base_pkg}.{node.module}" if node.module else base_pkg
                    if mod.startswith("nayraastra"):
                        imports.append(mod)

    return imports


@pytest.mark.unit
class TestArchitectureLayers:
    def test_core_imports_no_forbidden_layers(self) -> None:
        core_dir = _PACKAGE_ROOT / "core"
        forbidden = (
            "nayraastra.db",
            "nayraastra.cli",
            "nayraastra.modules",
            "nayraastra.adapters",
            "nayraastra.runtime",
        )

        violations: list[str] = []
        for py_file in core_dir.rglob("*.py"):
            imports = _get_imports(py_file)
            for imp in imports:
                if any(imp == f or imp.startswith(f + ".") for f in forbidden):
                    violations.append(f"{py_file.name} imports forbidden: {imp}")

        assert not violations, "Layer violations detected in core:\n" + "\n".join(violations)

    def test_adapters_imports_no_forbidden_layers(self) -> None:
        adapters_dir = _PACKAGE_ROOT / "adapters"
        forbidden = ("nayraastra.cli", "nayraastra.runtime", "nayraastra.modules")

        violations: list[str] = []
        for py_file in adapters_dir.rglob("*.py"):
            imports = _get_imports(py_file)
            for imp in imports:
                if any(imp == f or imp.startswith(f + ".") for f in forbidden):
                    violations.append(f"{py_file.name} imports forbidden: {imp}")

        assert not violations, "Layer violations in adapters:\n" + "\n".join(violations)

    def test_db_imports_no_forbidden_layers(self) -> None:
        db_dir = _PACKAGE_ROOT / "db"
        forbidden = (
            "nayraastra.cli",
            "nayraastra.runtime",
            "nayraastra.modules",
            "nayraastra.adapters",
        )

        violations: list[str] = []
        for py_file in db_dir.rglob("*.py"):
            imports = _get_imports(py_file)
            for imp in imports:
                if any(imp == f or imp.startswith(f + ".") for f in forbidden):
                    violations.append(f"{py_file.name} imports forbidden: {imp}")

        assert not violations, "Layer violations in db:\n" + "\n".join(violations)
