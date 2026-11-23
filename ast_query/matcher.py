"""Evaluating a parsed :class:`~ast_query.query.Query` against an AST."""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass
from typing import Any, Iterator, List, Optional, Tuple

from .query import Condition, Query, parse_query

__all__ = ["Match", "find", "matches", "resolve_path", "virtual_attribute", "VIRTUAL_ATTRIBUTES"]

_MISSING = object()

# Documented in the README; kept here so the CLI and playground can list them.
VIRTUAL_ATTRIBUTES = {
    "type": "Node class name, e.g. FunctionDef",
    "line": "First line of the node (1-based)",
    "end_line": "Last line of the node",
    "col": "Column offset of the node (0-based)",
    "lines": "Number of lines the node spans",
    "source": "The node's code, regenerated with ast.unparse",
    "argc": "Number of parameters (function) or arguments (call)",
    "docstring": "Docstring of a module, class or function",
    "name": "For calls, names and attributes: the dotted name, e.g. os.path.join",
}


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - extremely defensive
        return type(node).__name__


def virtual_attribute(node: ast.AST, name: str) -> Any:
    """Return a computed attribute that the ``ast`` module does not provide."""
    if name == "type":
        return type(node).__name__
    if name == "line":
        return getattr(node, "lineno", _MISSING)
    if name == "end_line":
        return getattr(node, "end_lineno", _MISSING)
    if name == "col":
        return getattr(node, "col_offset", _MISSING)
    if name == "lines":
        start, end = getattr(node, "lineno", None), getattr(node, "end_lineno", None)
        return _MISSING if start is None or end is None else end - start + 1
    if name == "source":
        return _unparse(node)
    if name == "argc":
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = node.args
            return (
                len(a.posonlyargs) + len(a.args) + len(a.kwonlyargs)
                + (1 if a.vararg else 0) + (1 if a.kwarg else 0)
            )
        if isinstance(node, ast.Call):
            return len(node.args) + len(node.keywords)
        return _MISSING
    if name == "docstring":
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            return ast.get_docstring(node) or ""
        return _MISSING
    if name == "name":
        if isinstance(node, ast.Call):
            return _unparse(node.func)
        if isinstance(node, (ast.Name, ast.Attribute)):
            return _unparse(node)
        return _MISSING
    return _MISSING


def resolve_path(node: ast.AST, path: List[str]) -> Tuple[bool, List[Any]]:
    """Follow a dotted attribute path from ``node``.

    Lists are flattened at every step, so ``names.name`` on an ``Import`` node
    yields every imported module name. Returns ``(found, values)`` where
    ``found`` is False if the attribute does not exist on any visited object.
    """
    current: List[Any] = [node]
    for segment in path:
        nxt: List[Any] = []
        found_any = False
        for obj in current:
            value = getattr(obj, segment, _MISSING) if not isinstance(obj, (str, int, float)) else _MISSING
            if value is _MISSING and isinstance(obj, ast.AST):
                value = virtual_attribute(obj, segment)
            if value is _MISSING:
                continue
            found_any = True
            if isinstance(value, list):
                nxt.extend(value)
            else:
                nxt.append(value)
        if not found_any:
            return False, []
        current = nxt
    return True, current


_OPERATOR_TYPES = (ast.operator, ast.cmpop, ast.unaryop, ast.boolop, ast.expr_context)


def _as_text(value: Any) -> str:
    if isinstance(value, _OPERATOR_TYPES):
        return type(value).__name__  # e.g. ops = 'Is', op = 'Add'
    if isinstance(value, ast.AST):
        return _unparse(value)
    return str(value)


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(_as_text(value))
    except ValueError:
        return None


def _compare(candidate: Any, cond: Condition, ignore_case: bool) -> bool:
    op, expected = cond.op, cond.value
    if op in ("<", "<=", ">", ">="):
        actual = _as_number(candidate)
        if actual is None:
            return False
        target = float(expected)  # validated by the parser
        return {
            "<": actual < target,
            "<=": actual <= target,
            ">": actual > target,
            ">=": actual >= target,
        }[op]

    if op in ("~=", "!~"):
        flags = re.IGNORECASE if ignore_case else 0
        return re.search(str(expected), _as_text(candidate), flags) is not None

    # "=" and "!="
    if isinstance(expected, (int, float)):
        actual_num = _as_number(candidate)
        if actual_num is not None:
            return actual_num == float(expected)
    left, right = _as_text(candidate), str(expected)
    if ignore_case:
        left, right = left.lower(), right.lower()
    return left == right


def _condition_holds(node: ast.AST, cond: Condition, ignore_case: bool) -> bool:
    found, values = resolve_path(node, cond.path)
    if cond.op is None:
        result = found and any(bool(v) for v in values)
    elif not found:
        result = False
    elif cond.op in ("!=", "!~"):
        positive = Condition(cond.path, "=" if cond.op == "!=" else "~=", cond.value)
        result = not any(_compare(v, positive, ignore_case) for v in values)
    else:
        result = any(_compare(v, cond, ignore_case) for v in values)
    return not result if cond.negate else result


def matches(node: ast.AST, query: Query, ignore_case: bool = False) -> bool:
    """Return True if ``node`` satisfies ``query``."""
    if not isinstance(node, query.types):
        return False
    return all(_condition_holds(node, c, ignore_case) for c in query.conditions)


@dataclass
class Match:
    """A node that satisfied the query, with its location and source text."""

    node: ast.AST
    type: str
    line: int
    col: int
    end_line: int
    end_col: int
    code: str
    path: str = "<string>"

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "type": self.type,
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line,
            "end_col": self.end_col,
            "code": self.code,
        }


def _iter_nodes(tree: ast.AST) -> Iterator[ast.AST]:
    yield from ast.walk(tree)


def find(query: "Query | str", source: str, path: str = "<string>", ignore_case: bool = False) -> List[Match]:
    """Run ``query`` over Python ``source`` and return matches in source order.

    Only nodes with a position in the file (statements, expressions, arguments,
    keywords, ...) are reported; ``find module`` reports the whole file.

    >>> [m.line for m in find("find function", "def a(): pass\\n\\ndef b(): pass")]
    [1, 3]
    """
    if isinstance(query, str):
        query = parse_query(query)
    tree = ast.parse(source, filename=path)
    lines = source.splitlines()
    results: List[Match] = []
    for node in _iter_nodes(tree):
        if not matches(node, query, ignore_case):
            continue
        if isinstance(node, ast.Module):
            end = max(len(lines), 1)
            results.append(Match(node, "Module", 1, 0, end, len(lines[-1]) if lines else 0, source, path))
            continue
        if not hasattr(node, "lineno"):
            continue
        line, col = node.lineno, node.col_offset
        end_line = getattr(node, "end_lineno", None) or line
        end_col = getattr(node, "end_col_offset", None)
        if end_col is None:
            end_col = len(lines[end_line - 1]) if end_line - 1 < len(lines) else col
        segment = ast.get_source_segment(source, node)
        code = textwrap.dedent(" " * col + segment).lstrip() if segment else _unparse(node)
        results.append(Match(node, type(node).__name__, line, col, end_line, end_col, code, path))
    results.sort(key=lambda m: (m.line, m.col, -(m.end_line), -(m.end_col)))
    return results


# Backwards compatible visitor used by earlier versions of AST-Query.
class QueryVisitor(ast.NodeVisitor):
    """Collects matching nodes in ``self.matches`` (legacy API)."""

    def __init__(self, parsed_query: "Query | str", ignore_case: bool = False):
        self.query = parse_query(parsed_query) if isinstance(parsed_query, str) else parsed_query
        self.ignore_case = ignore_case
        self.matches: List[ast.AST] = []

    def generic_visit(self, node: ast.AST) -> None:
        if matches(node, self.query, self.ignore_case):
            self.matches.append(node)
        super().generic_visit(node)
