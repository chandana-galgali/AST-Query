r"""AST-Query: query the abstract syntax tree of Python code.

>>> from ast_query import find
>>> [m.line for m in find("find call where func = 'print'", "x = 1\nprint(x)\n")]
[2]
"""

__version__ = "1.0.0"

from .matcher import Match, QueryVisitor, find, matches  # noqa: E402
from .query import Query, QuerySyntaxError, parse_query  # noqa: E402

__all__ = ["Match", "Query", "QuerySyntaxError", "QueryVisitor", "find", "matches", "parse_query", "__version__"]
