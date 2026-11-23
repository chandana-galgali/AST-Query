"""Reading Python files and collecting them from directories."""

from __future__ import annotations

import ast
import os
import tokenize
from typing import Iterable, Iterator

__all__ = ["read_source", "parse_file_to_ast", "iter_python_files", "SKIP_DIRS"]

SKIP_DIRS = {
    "__pycache__", "node_modules", "venv", "env", "build", "dist", "site-packages",
}


def read_source(filepath: str) -> str:
    """Read a Python file, honouring PEP 263 encoding declarations."""
    with tokenize.open(filepath) as handle:
        return handle.read()


def parse_file_to_ast(filepath: str) -> ast.AST:
    """Read a Python file and return the root node of its AST."""
    return ast.parse(read_source(filepath), filename=filepath)


def iter_python_files(paths: Iterable[str]) -> Iterator[str]:
    """Yield ``.py`` files from a mix of file and directory paths.

    Directories are walked recursively in sorted order, skipping hidden
    directories (``.git``, ``.venv``, ...) and common build/vendor folders.
    Files given explicitly are always yielded, whatever their extension.
    """
    for path in paths:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
                for name in sorted(files):
                    if name.endswith((".py", ".pyi")):
                        yield os.path.join(root, name)
        else:
            yield path
