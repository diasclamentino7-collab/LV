"""Reject destructive Alembic operations before they reach an environment.

This guard deliberately favours safety. Any exceptional data-retention change
must be handled outside the normal migration workflow and explicitly approved.
"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_OPERATIONS = frozenset({"drop_table", "drop_column"})
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def forbidden_calls(path: Path) -> list[str]:
    """Return forbidden Alembic operation names used by a migration file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in FORBIDDEN_OPERATIONS:
            found.append(f"{path.name}:{node.lineno}: {node.func.attr}")
    return found


def main() -> int:
    violations = [
        violation for path in MIGRATIONS_DIR.glob("*.py") for violation in forbidden_calls(path)
    ]
    if violations:
        print("Destructive migration operation detected:", *violations, sep="\n")
        return 1
    print("Migration safety check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
