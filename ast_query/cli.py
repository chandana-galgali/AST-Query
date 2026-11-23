"""Command-line interface: ``astq QUERY [PATH ...]``."""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from typing import List, Optional, Sequence

from . import __version__
from .matcher import VIRTUAL_ATTRIBUTES, Match, find
from .parser import iter_python_files, read_source
from .query import TYPE_ALIASES, QuerySyntaxError, _AST_CLASSES, _snake, parse_query

EPILOG = """\
examples:
  astq "find function" src/
  astq "find class where name = 'DataProcessor'" example.py
  astq "find call where func = 'print'" .
  astq "find function where lines > 30 and not docstring" .
  astq "find import where names.name ~= '^os'" .
  astq --dump example.py

exit status: 0 if anything matched, 1 if nothing matched, 2 on error.
"""


class Style:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def path(self, t: str) -> str:
        return self._wrap("35", t)

    def num(self, t: str) -> str:
        return self._wrap("32", t)

    def kind(self, t: str) -> str:
        return self._wrap("36", t)

    def hit(self, t: str) -> str:
        return self._wrap("1;31", t)

    def dim(self, t: str) -> str:
        return self._wrap("2", t)

    def err(self, t: str) -> str:
        return self._wrap("1;31", t)


def _highlight_line(line: str, match: Match, style: Style) -> str:
    """Highlight the matched span on the first line. AST columns are UTF-8 byte offsets."""
    raw = line.encode("utf-8")
    start = match.col
    end = match.end_col if match.end_line == match.line else len(raw)
    before = raw[:start].decode("utf-8", "replace")
    middle = raw[start:end].decode("utf-8", "replace")
    after = raw[end:].decode("utf-8", "replace")
    return (before + style.hit(middle) + after).strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="astq",
        description="Query the abstract syntax tree of Python code with a small, readable query language.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="?", help="query string, e.g. \"find function where name = 'main'\"")
    parser.add_argument("paths", nargs="*", help="files or directories to search (default: current directory)")
    parser.add_argument("-i", "--ignore-case", action="store_true", help="case-insensitive value comparisons")
    parser.add_argument("-c", "--count", action="store_true", help="print only the number of matches")
    parser.add_argument("-l", "--files-with-matches", action="store_true", help="print only names of files with matches")
    parser.add_argument("-s", "--show-code", action="store_true", help="print the full source of each match")
    parser.add_argument("--json", action="store_true", help="print matches as JSON")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto", help="colorize output (default: auto)")
    parser.add_argument("--dump", metavar="FILE", help="print the AST of FILE to discover node types and attributes")
    parser.add_argument("--list-types", action="store_true", help="list node types, aliases and virtual attributes")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _list_types() -> str:
    out = ["Aliases:"]
    width = max(len(a) for a in TYPE_ALIASES)
    for alias, classes in TYPE_ALIASES.items():
        out.append(f"  {alias.ljust(width)}  {', '.join(c.__name__ for c in classes)}")
    out.append("")
    out.append("Node types (snake_case or ClassName both work):")
    names = sorted({_snake(c.__name__) for c in _AST_CLASSES.values()})
    line = "  "
    for name in names:
        if len(line) + len(name) + 2 > 88:
            out.append(line.rstrip())
            line = "  "
        line += name + "  "
    out.append(line.rstrip())
    out.append("")
    out.append("Virtual attributes (usable on any node where they make sense):")
    width = max(len(a) for a in VIRTUAL_ATTRIBUTES)
    for attr, desc in VIRTUAL_ATTRIBUTES.items():
        out.append(f"  {attr.ljust(width)}  {desc}")
    return "\n".join(out)


def _legacy_order(argv: List[str]) -> List[str]:
    """Support the v0.1 calling convention: ``main.py <file> "<query>"``."""
    positional: List[int] = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
        elif arg in ("--color", "--dump"):
            skip_next = True
        elif not arg.startswith("-"):
            positional.append(i)
    if len(positional) == 2:
        first, second = (argv[i] for i in positional)
        if (
            os.path.isfile(first)
            and second.strip().lower().startswith("find")
            and not first.strip().lower().startswith("find")
        ):
            argv = list(argv)
            argv[positional[0]], argv[positional[1]] = second, first
    return argv


def main(argv: Optional[Sequence[str]] = None) -> int:
    args_list = _legacy_order(list(sys.argv[1:] if argv is None else argv))
    parser = _build_parser()
    args = parser.parse_args(args_list)

    color = args.color == "always" or (args.color == "auto" and sys.stdout.isatty() and not os.environ.get("NO_COLOR"))
    style = Style(color and not args.json)

    if args.list_types:
        print(_list_types())
        return 0

    if args.dump:
        try:
            tree = ast.parse(read_source(args.dump), filename=args.dump)
        except (OSError, SyntaxError) as exc:
            print(style.err(f"astq: {exc}"), file=sys.stderr)
            return 2
        print(ast.dump(tree, indent=2))
        return 0

    if not args.query:
        parser.print_usage(sys.stderr)
        print("astq: error: a query is required (try: astq \"find function\" .)", file=sys.stderr)
        return 2

    try:
        query = parse_query(args.query)
    except QuerySyntaxError as exc:
        print(style.err(f"astq: {exc}"), file=sys.stderr)
        return 2

    paths = args.paths or ["."]
    all_matches: List[Match] = []
    files_with_matches: List[str] = []
    files_searched = 0
    had_error = False

    for path in iter_python_files(paths):
        try:
            source = read_source(path)
            found = find(query, source, path=path, ignore_case=args.ignore_case)
        except FileNotFoundError:
            print(style.err(f"astq: {path}: no such file or directory"), file=sys.stderr)
            had_error = True
            continue
        except SyntaxError as exc:
            print(style.dim(f"astq: skipping {path}: syntax error on line {exc.lineno}"), file=sys.stderr)
            continue
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print(style.dim(f"astq: skipping {path}: {exc}"), file=sys.stderr)
            continue
        files_searched += 1
        if not found:
            continue
        files_with_matches.append(path)
        all_matches.extend(found)

        if args.json or args.count or args.files_with_matches:
            continue
        lines = source.splitlines()
        for m in found:
            location = f"{style.path(path)}:{style.num(str(m.line))}:{style.num(str(m.col + 1))}"
            text = _highlight_line(lines[m.line - 1], m, style) if 0 < m.line <= len(lines) else ""
            print(f"{location}  {style.kind(m.type)}  {text}")
            if args.show_code:
                for code_line in m.code.splitlines():
                    print(style.dim("    │ ") + code_line)

    if args.json:
        print(json.dumps([m.to_dict() for m in all_matches], indent=2))
    elif args.count:
        print(len(all_matches))
    elif args.files_with_matches:
        for path in files_with_matches:
            print(style.path(path))
    else:
        noun = "match" if len(all_matches) == 1 else "matches"
        files = "file" if files_searched == 1 else "files"
        print(style.dim(f"\n{len(all_matches)} {noun} in {len(files_with_matches)} of {files_searched} {files}"))

    if had_error:
        return 2
    return 0 if all_matches else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
