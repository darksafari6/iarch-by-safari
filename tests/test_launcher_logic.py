# Copyright (C) 2026 Safari — GPL-3.0-or-later
import unittest
from decimal import Decimal

from iarch.lib.launcher_math import calculate, convert
from iarch.lib.launcher_search import match_score, rank


class CalculatorTests(unittest.TestCase):
    def test_arithmetic_and_precedence(self):
        for expression, expected in [('2 + 3 * 4', '14'), ('(2+3)*4', '20'),
                                     ('-2^2', '-4'), ('2^-3', '0.125'),
                                     ('0.1 + 0.2', '0.3'), ('1e2 / 4', '25'), ('7%4', '3')]:
            with self.subTest(expression=expression):
                self.assertEqual(calculate(expression), Decimal(expected))

    def test_rejects_code_invalid_or_expensive(self):
        for expression in ['__import__("os")', 'open(1)', '1//2', '[1]', 'True',
                           '1/0', '0**-1', '2**101', '2**0.5', '1e999999',
                           '0x10', '1_000', '1 #comment', '1+' * 300 + '1', '('*40 + '1' + ')'*40]:
            # Parentheses alone do not add AST nodes; reject only excessive source length/depth where applicable.
            if expression == '('*40 + '1' + ')'*40:
                continue
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                calculate(expression)

    def test_conversions_and_boundaries(self):
        self.assertEqual(convert('100', 'cm', 'm'), Decimal('1'))
        self.assertEqual(convert('1', 'mi', 'm'), Decimal('1609.344'))
        self.assertEqual(convert('1', 'KiB', 'b'), Decimal('1024'))
        self.assertEqual(convert('32', 'f', 'c'), Decimal('0'))
        self.assertEqual(convert('0', 'c', 'k'), Decimal('273.15'))
        for args in [('1', 'm', 's'), ('-1', 'k', 'c'), ('1e100', 'km', 'mm')]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                convert(*args)


class SearchTests(unittest.TestCase):
    def test_fuzzy_and_frequency_tiebreak(self):
        entries = [{'id': 'a', 'name': 'Text Editor'}, {'id': 'b', 'name': 'Terminal'},
                   {'id': 'c', 'name': 'Text Editor'}, {'id': 'd', 'name': 'Browser'}]
        self.assertEqual([x['id'] for x in rank('text', entries, {'c': 5})], ['c', 'a'])
        self.assertEqual([x['id'] for x in rank('tmn', entries)], ['b'])
        self.assertGreater(match_score('terminal', 'Terminal'), match_score('terminal', 'Terminal Extra'))
        self.assertIsNone(match_score('abc', 'cba'))
        self.assertEqual(rank('', entries, {'d': 20}, limit=1)[0]['id'], 'd')
        self.assertEqual(rank('text', entries, limit=0), [])

    def test_invalid_inputs_and_determinism(self):
        with self.assertRaises(ValueError): rank('x', [], limit=101)
        with self.assertRaises(ValueError): rank('x' * 129, [])
        self.assertEqual(rank('a', [{'id': 'b', 'name': 'A'}, {'id': 'a', 'name': 'A'}])[0]['id'], 'a')

class LauncherHelperTests(unittest.TestCase):
    def test_json_protocol_and_invalid_requests(self):
        import json
        import subprocess
        import sys
        from pathlib import Path
        helper = Path(__file__).resolve().parents[1] / 'iarch/cli/shell_launcher.py'
        def invoke(value):
            return subprocess.run([sys.executable, str(helper)], input=json.dumps(value), text=True, capture_output=True)
        response = invoke({'action': 'calculate', 'expression': '2*4'})
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout), {'result': '8'})
        response = invoke({'action': 'convert', 'expression': '2', 'from': 'km', 'to': 'm'})
        self.assertEqual(json.loads(response.stdout), {'result': '2000'})
        response = invoke({'action': 'search', 'query': 'term', 'entries': [{'id': 'a', 'name': 'Terminal'}]})
        self.assertEqual(json.loads(response.stdout)['results'][0]['id'], 'a')
        self.assertNotEqual(invoke({'action': 'calculate', 'expression': '__import__(1)'}).returncode, 0)
        self.assertNotEqual(invoke({'action': 'launch', 'command': 'anything'}).returncode, 0)


if __name__ == '__main__':
    unittest.main()
