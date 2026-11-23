"""Parsing of the AST-Query language.

Grammar (keywords are case-insensitive)::

    query      := "find" types ["where" condition ("and" condition)*]
    types      := type (("," | "or") type)*
    condition  := ["not"] path [operator value]
    path       := name ("." name)*
    operator   := "=" | "==" | "!=" | "~=" | "!~" | "<" | "<=" | ">" | ">="
    value      := 'single quoted' | "double quoted" | number | bareword

Examples::

    find function
    find function_def where name = 'process'
    find call where func = 'print'
    find function where lines > 20 and not docstring
    find class where bases ~= 'Exception$'
    find for_loop, while_loop
"""

from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Type, Union

__all__ = ["Condition", "Query", "QuerySyntaxError", "parse_query", "resolve_type", "TYPE_ALIASES"]

Number = Union[int, float]


class QuerySyntaxError(ValueError):
    """Raised when a query string cannot be parsed."""


def _types(*names: str) -> Tuple[Type[ast.AST], ...]:
    """Collect AST classes by name, skipping any this Python version lacks."""
    return tuple(getattr(ast, n) for n in names if hasattr(ast, n))


# Friendly names that map to one or more AST node classes.
TYPE_ALIASES: Dict[str, Tuple[Type[ast.AST], ...]] = {
    "any": (ast.AST,),
    "node": (ast.AST,),
    "*": (ast.AST,),
    "function": _types("FunctionDef", "AsyncFunctionDef"),
    "def": _types("FunctionDef", "AsyncFunctionDef"),
    "class": _types("ClassDef"),
    "call": _types("Call"),
    "import": _types("Import", "ImportFrom"),
    "loop": _types("For", "AsyncFor", "While"),
    "for_loop": _types("For", "AsyncFor"),
    "for": _types("For", "AsyncFor"),
    "while_loop": _types("While"),
    "while": _types("While"),
    "if": _types("If"),
    "try": _types("Try", "TryStar"),
    "with": _types("With", "AsyncWith"),
    "assign": _types("Assign", "AugAssign", "AnnAssign"),
    "return": _types("Return"),
    "yield": _types("Yield", "YieldFrom"),
    "await": _types("Await"),
    "raise": _types("Raise"),
    "assert": _types("Assert"),
    "lambda": _types("Lambda"),
    "comprehension": _types("ListComp", "SetComp", "DictComp", "GeneratorExp"),
    "string": _types("JoinedStr", "Constant"),
    "fstring": _types("JoinedStr"),
    "variable": _types("Name"),
}

# Every concrete and abstract node class exposed by the ast module,
# keyed by its lowercased name with underscores removed.
_AST_CLASSES: Dict[str, Type[ast.AST]] = {
    name.lower(): obj
    for name, obj in vars(ast).items()
    if isinstance(obj, type) and issubclass(obj, ast.AST) and not name.startswith("_")
}


def resolve_type(name: str) -> Tuple[Type[ast.AST], ...]:
    """Turn a user-facing type name into a tuple of AST classes.

    Accepts aliases (``function``, ``for_loop``), snake_case class names
    (``function_def``, ``import_from``) and exact class names (``FunctionDef``).
    """
    key = name.strip()
    lowered = key.lower()
    if lowered in TYPE_ALIASES:
        return TYPE_ALIASES[lowered]
    normalized = lowered.replace("_", "")
    if normalized in _AST_CLASSES:
        return (_AST_CLASSES[normalized],)

    candidates = list(TYPE_ALIASES) + [_snake(c.__name__) for c in _AST_CLASSES.values()]
    suggestion = difflib.get_close_matches(lowered, candidates, n=1)
    hint = f" Did you mean '{suggestion[0]}'?" if suggestion else ""
    raise QuerySyntaxError(f"Unknown node type '{name}'.{hint} Run 'astq --list-types' to see all types.")


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


OPERATORS = ("==", "!=", "~=", "!~", "<=", ">=", "=", "<", ">")

_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<string>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
      | (?P<op>==|!=|~=|!~|<=|>=|=|<|>)
      | (?P<comma>,)
      | (?P<number>-?\d+(?:\.\d+)?(?![\w.]))
      | (?P<word>[A-Za-z_*][\w.*]*)
    )
    """,
    re.VERBOSE,
)


@dataclass
class Condition:
    """A single ``where`` clause test such as ``name = 'main'``."""

    path: List[str]
    op: Optional[str] = None  # None means "attribute is truthy"
    value: Union[str, Number, None] = None
    negate: bool = False

    def __str__(self) -> str:
        text = ".".join(self.path)
        if self.op:
            text += f" {self.op} {self.value!r}"
        return f"not {text}" if self.negate else text


@dataclass
class Query:
    """A parsed query: which node types to find and which conditions must hold."""

    type_names: List[str]
    types: Tuple[Type[ast.AST], ...]
    conditions: List[Condition] = field(default_factory=list)
    source: str = ""

    @classmethod
    def parse(cls, text: str) -> "Query":
        return parse_query(text)


def _tokenize(text: str) -> List[Tuple[str, str]]:
    tokens: List[Tuple[str, str]] = []
    pos = 0
    text = text.rstrip()
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if not match or match.end() == pos:
            snippet = text[pos:].strip()[:20]
            raise QuerySyntaxError(f"Unexpected input near '{snippet}' (column {pos + 1}).")
        kind = match.lastgroup
        assert kind is not None
        tokens.append((kind, match.group(kind)))
        pos = match.end()
    return tokens


def _unquote(raw: str) -> str:
    """Strip the quotes; only escaped quote characters are unescaped so regexes keep their backslashes."""
    quote, body = raw[0], raw[1:-1]
    return body.replace("\\" + quote, quote)


def parse_query(text: str) -> Query:
    """Parse a query string into a :class:`Query`.

    >>> q = parse_query("find function where name = 'main'")
    >>> q.type_names, str(q.conditions[0])
    (['function'], "name = 'main'")
    """
    tokens = _tokenize(text)
    i = 0

    def peek(offset: int = 0) -> Tuple[str, str]:
        j = i + offset
        return tokens[j] if j < len(tokens) else ("eof", "")

    def is_keyword(token: Tuple[str, str], word: str) -> bool:
        return token[0] == "word" and token[1].lower() == word

    if not is_keyword(peek(), "find"):
        raise QuerySyntaxError("A query must start with 'find', e.g. find function where name = 'main'")
    i += 1

    type_names: List[str] = []
    while True:
        kind, value = peek()
        if kind != "word" or value.lower() in ("where", "and", "or"):
            raise QuerySyntaxError("Expected a node type after 'find' (e.g. function, class, call).")
        type_names.append(value)
        i += 1
        nxt = peek()
        if nxt[0] == "comma" or is_keyword(nxt, "or"):
            i += 1
            continue
        break

    types: Tuple[Type[ast.AST], ...] = ()
    for name in type_names:
        for cls in resolve_type(name):
            if cls not in types:
                types += (cls,)

    conditions: List[Condition] = []
    if is_keyword(peek(), "where"):
        i += 1
        while True:
            negate = False
            if is_keyword(peek(), "not"):
                negate = True
                i += 1
            kind, value = peek()
            if kind != "word":
                raise QuerySyntaxError("Expected an attribute name after 'where'/'and' (e.g. name, func, lines).")
            path = [p for p in value.split(".") if p]
            i += 1

            op: Optional[str] = None
            cond_value: Union[str, Number, None] = None
            if peek()[0] == "op":
                op = peek()[1]
                if op == "==":
                    op = "="
                i += 1
                vkind, vraw = peek()
                if vkind == "string":
                    cond_value = _unquote(vraw)
                elif vkind == "number":
                    cond_value = float(vraw) if "." in vraw else int(vraw)
                elif vkind == "word":
                    cond_value = vraw
                else:
                    raise QuerySyntaxError(f"Expected a value after '{op}'.")
                i += 1
                if op in ("<", "<=", ">", ">=") and not isinstance(cond_value, (int, float)):
                    raise QuerySyntaxError(f"Operator '{op}' needs a number, got {cond_value!r}.")
                if op in ("~=", "!~"):
                    try:
                        re.compile(str(cond_value))
                    except re.error as exc:
                        raise QuerySyntaxError(f"Invalid regular expression {cond_value!r}: {exc}") from None

            conditions.append(Condition(path=path, op=op, value=cond_value, negate=negate))
            if is_keyword(peek(), "and"):
                i += 1
                continue
            break

    if i < len(tokens):
        raise QuerySyntaxError(f"Unexpected '{tokens[i][1]}'. Combine conditions with 'and'.")

    return Query(type_names=type_names, types=types, conditions=conditions, source=text.strip())
