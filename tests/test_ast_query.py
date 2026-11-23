"""Tests for AST-Query. Run with ``python -m unittest`` or ``pytest``."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ast_query import QuerySyntaxError, QueryVisitor, find, parse_query
from ast_query.cli import main
from ast_query.parser import parse_file_to_ast

SAMPLE = '''\
import os
from pathlib import Path


class DataProcessor:
    """Cleans records."""

    def process(self, data):
        if not data:
            return None
        for item in data:
            print(f"Processing {item}")
        while False:
            pass
        return True

    @staticmethod
    def load(path, encoding="utf-8", strict=False, retries=3, timeout=10):
        return os.path.join(path)


class ProcessingError(Exception):
    pass


async def fetch():
    async for chunk in stream():
        await chunk


def helper_function():
    pass
'''


def lines(query, source=SAMPLE, **kw):
    return [m.line for m in find(query, source, **kw)]


class TypeMatchingTests(unittest.TestCase):
    def test_snake_case_class_name(self):
        self.assertEqual(lines("find function_def"), [8, 18, 31])

    def test_exact_class_name(self):
        self.assertEqual(lines("find FunctionDef"), [8, 18, 31])

    def test_function_alias_includes_async(self):
        self.assertEqual(lines("find function"), [8, 18, 26, 31])

    def test_for_loop_alias(self):
        self.assertEqual(lines("find for_loop"), [11, 27])

    def test_multiple_types(self):
        self.assertEqual(lines("find for_loop, while_loop"), [11, 13, 27])
        self.assertEqual(lines("find for or while"), [11, 13, 27])

    def test_abstract_type(self):
        self.assertIn(9, lines("find stmt"))

    def test_unknown_type_suggests(self):
        with self.assertRaises(QuerySyntaxError) as ctx:
            parse_query("find functon")
        self.assertIn("function", str(ctx.exception))


class ConditionTests(unittest.TestCase):
    def test_equality_is_case_sensitive(self):
        self.assertEqual(lines("find class where name = 'DataProcessor'"), [5])
        self.assertEqual(lines("find class where name = 'dataprocessor'"), [])

    def test_ignore_case(self):
        self.assertEqual(lines("find class where name = 'dataprocessor'", ignore_case=True), [5])

    def test_double_quotes_and_barewords(self):
        self.assertEqual(lines('find function where name = "process"'), [8])
        self.assertEqual(lines("find function where name = process"), [8])

    def test_not_equal(self):
        self.assertEqual(lines("find class where name != 'DataProcessor'"), [22])

    def test_and(self):
        self.assertEqual(lines("find function where lines > 2 and name ~= '^pro'"), [8])

    def test_regex(self):
        self.assertEqual(lines("find function where name ~= '^(load|fetch)$'"), [18, 26])
        self.assertEqual(lines("find class where name !~ 'Error'"), [5])

    def test_ast_node_values_compare_as_source(self):
        self.assertEqual(lines("find call where func = 'print'"), [12])
        self.assertEqual(lines("find call where func = 'os.path.join'"), [19])
        self.assertEqual(lines("find class where bases = 'Exception'"), [22])

    def test_lists_match_any_element(self):
        self.assertEqual(lines("find function where decorator_list = 'staticmethod'"), [18])
        self.assertEqual(lines("find import where names.name = 'Path'"), [2])

    def test_dotted_paths(self):
        self.assertEqual(lines("find call where func.attr = 'join'"), [19])
        self.assertEqual(lines("find function where args.args.arg = 'retries'"), [18])

    def test_truthy_and_not(self):
        self.assertEqual(lines("find class where docstring"), [5])
        self.assertEqual(lines("find class where not docstring"), [22])

    def test_numeric_comparisons(self):
        self.assertEqual(lines("find function where argc >= 5"), [18])
        self.assertEqual(lines("find constant where value = 3"), [18])
        self.assertEqual(lines("find function where line < 10"), [8])

    def test_operators_compare_by_class_name(self):
        src = "if a is 0:\n    pass\nb = 1 + 2\n"
        self.assertEqual(lines("find compare where ops = 'Is' and comparators.value = 0", src), [1])
        self.assertEqual(lines("find bin_op where op = 'Add'", src), [3])

    def test_regex_backslashes_survive_quoting(self):
        self.assertEqual(lines(r"find call where name ~= '^os\.path'"), [19])
        self.assertEqual(lines(r"find call where name ~= '^os\.pat$'"), [])

    def test_virtual_name_for_calls(self):
        self.assertEqual(lines("find call where name = 'os.path.join'"), [19])

    def test_missing_attribute_never_matches(self):
        self.assertEqual(lines("find if where name = 'x'"), [])
        self.assertEqual(lines("find if where name != 'x'"), [])


class SyntaxTests(unittest.TestCase):
    def test_must_start_with_find(self):
        with self.assertRaises(QuerySyntaxError):
            parse_query("search function")

    def test_needs_and_between_conditions(self):
        with self.assertRaises(QuerySyntaxError):
            parse_query("find function where name = 'a' name = 'b'")

    def test_numeric_operator_needs_number(self):
        with self.assertRaises(QuerySyntaxError):
            parse_query("find function where lines > 'many'")

    def test_bad_regex(self):
        with self.assertRaises(QuerySyntaxError):
            parse_query("find function where name ~= '('")

    def test_escaped_quotes(self):
        q = parse_query(r"find constant where value = 'it\'s'")
        self.assertEqual(q.conditions[0].value, "it's")


class MatchTests(unittest.TestCase):
    def test_match_positions_and_code(self):
        (m,) = find("find call where func = 'print'", SAMPLE)
        self.assertEqual((m.line, m.col, m.end_line), (12, 12, 12))
        self.assertEqual(m.code, 'print(f"Processing {item}")')
        self.assertEqual(m.type, "Call")

    def test_multiline_code_is_dedented(self):
        (m,) = find("find function where name = 'process'", SAMPLE)
        self.assertTrue(m.code.startswith("def process(self, data):\n    if not data:"))

    def test_legacy_visitor(self):
        visitor = QueryVisitor("find function_def where name = 'process'")
        visitor.visit(parse_file_to_ast_from_string(SAMPLE))
        self.assertEqual([n.lineno for n in visitor.matches], [8])


def parse_file_to_ast_from_string(source):
    import ast

    return ast.parse(source)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.file = os.path.join(self.dir, "sample.py")
        with open(self.file, "w", encoding="utf-8") as fh:
            fh.write(SAMPLE)
        os.makedirs(os.path.join(self.dir, ".venv"))
        with open(os.path.join(self.dir, ".venv", "skip.py"), "w") as fh:
            fh.write("def hidden(): pass\n")
        with open(os.path.join(self.dir, "broken.py"), "w") as fh:
            fh.write("def broken(:\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--color", "never", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_search_directory(self):
        code, out, err = self.run_cli("find function", self.dir)
        self.assertEqual(code, 0)
        self.assertIn("sample.py:8:5  FunctionDef  def process(self, data):", out)
        self.assertNotIn("hidden", out)
        self.assertIn("skipping", err)

    def test_count_and_exit_codes(self):
        self.assertEqual(self.run_cli("-c", "find class", self.file)[1].strip(), "2")
        self.assertEqual(self.run_cli("find class where name = 'Nope'", self.file)[0], 1)
        self.assertEqual(self.run_cli("find nonsense", self.file)[0], 2)

    def test_json(self):
        code, out, _ = self.run_cli("--json", "find call where func = 'print'", self.file)
        data = json.loads(out)
        self.assertEqual(data[0]["line"], 12)
        self.assertEqual(data[0]["code"], 'print(f"Processing {item}")')

    def test_legacy_argument_order(self):
        code, out, _ = self.run_cli(self.file, "find function_def where name='process'")
        self.assertEqual(code, 0)
        self.assertIn(":8:5", out)

    def test_list_types_and_dump(self):
        self.assertIn("for_loop", self.run_cli("--list-types")[1])
        self.assertIn("FunctionDef(", self.run_cli("--dump", self.file)[1])

    def test_parse_file_to_ast(self):
        self.assertEqual(type(parse_file_to_ast(self.file)).__name__, "Module")


if __name__ == "__main__":
    unittest.main()
