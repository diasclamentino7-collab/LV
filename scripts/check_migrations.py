"""Reject destructive Alembic operations before they reach an environment.

This guard deliberately favours safety. Any exceptional data-retention change
must be handled outside the normal migration workflow and explicitly approved.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

FORBIDDEN_OPERATIONS = frozenset({"drop_table", "drop_column", "rename_table"})
SQL_EXECUTION_METHODS = frozenset({"execute", "exec_driver_sql"})
FORBIDDEN_SQL = (
    ("TRUNCATE", re.compile(r"\bTRUNCATE(?:\s+TABLE)?\b", re.IGNORECASE)),
    ("DROP", re.compile(r"\bDROP\b", re.IGNORECASE)),
    ("DELETE", re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE)),
)
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _without_sql_comments(sql: str) -> str:
    """Remove SQL comments so documentation does not create false positives."""
    without_blocks = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\r\n]*", " ", without_blocks)


def _assigned_strings(tree: ast.AST) -> dict[str, str]:
    """Collect simple SQL constants referenced by an execute call."""
    values: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                values[target.id] = value.value
    return values


def _string_fragments(node: ast.AST, assigned: dict[str, str]) -> list[str]:
    """Return statically visible string fragments from an SQL expression."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name) and node.id in assigned:
        return [assigned[node.id]]
    if isinstance(node, ast.JoinedStr):
        return [
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        ]
    fragments: list[str] = []
    for child in ast.iter_child_nodes(node):
        fragments.extend(_string_fragments(child, assigned))
    return fragments


def _forbidden_sql(call: ast.Call, assigned: dict[str, str]) -> set[str]:
    """Return destructive SQL keywords visible in an execution call."""
    sql = " ".join(
        fragment
        for argument in (*call.args, *(keyword.value for keyword in call.keywords))
        for fragment in _string_fragments(argument, assigned)
    )
    sql = _without_sql_comments(sql)
    return {name for name, pattern in FORBIDDEN_SQL if pattern.search(sql)}


def forbidden_calls(path: Path) -> list[str]:
    """Return destructive Alembic or raw SQL operations used by a migration."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assigned = _assigned_strings(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in FORBIDDEN_OPERATIONS:
            found.append(f"{path.name}:{node.lineno}: {node.func.attr}")
        if node.func.attr in SQL_EXECUTION_METHODS:
            found.extend(
                f"{path.name}:{node.lineno}: raw SQL {keyword}"
                for keyword in sorted(_forbidden_sql(node, assigned))
            )
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
