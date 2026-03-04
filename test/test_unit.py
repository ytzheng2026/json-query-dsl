"""
单元测试：Lexer / Parser / Evaluator 各模块独立测试
====================================================
与 test_json_dsl.py 的端到端测试不同，本文件针对三个模块分别验证，
以便出 bug 时能精确定位是哪一层出了问题。
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from json_dsl import (
    Lexer, Parser, DSLEvaluator, DSLSyntaxError,
    Query, Path, GetField, IndexAccess, Filter, FuncCall, BinOp, Literal, Ident,
)


# ──────────────────────────────────────────
# Lexer 单元测试
# ──────────────────────────────────────────

class TestLexer(unittest.TestCase):

    def test_simple_path_tokens(self):
        """users.name => 3 tokens: ID, DOT, ID"""
        tokens = Lexer("users.name").tokens
        kinds = [t[0] for t in tokens]
        self.assertEqual(kinds, ['ID', 'DOT', 'ID'])

    def test_index_access_tokens(self):
        """users[0] => ID LBRACK NUM RBRACK"""
        tokens = Lexer("users[0]").tokens
        kinds = [t[0] for t in tokens]
        self.assertEqual(kinds, ['ID', 'LBRACK', 'NUM', 'RBRACK'])
        self.assertEqual(tokens[2][1], 0)  # NUM 的值是 int 0

    def test_filter_tokens(self):
        """users[age > 25] => ID LBRACK ID OP NUM RBRACK"""
        tokens = Lexer("users[age > 25]").tokens
        kinds = [t[0] for t in tokens]
        self.assertEqual(kinds, ['ID', 'LBRACK', 'ID', 'OP', 'NUM', 'RBRACK'])
        self.assertEqual(tokens[3][1], '>')
        self.assertEqual(tokens[4][1], 25)

    def test_bool_and_null_conversion(self):
        """true/false/null 应被转换为 Python 值"""
        tokens = Lexer("true false null").tokens
        self.assertEqual(tokens[0][1], True)
        self.assertEqual(tokens[1][1], False)
        self.assertIsNone(tokens[2][1])

    def test_string_stripping(self):
        """字符串引号应被去掉"""
        tokens = Lexer('"hello"').tokens
        self.assertEqual(tokens[0][0], 'STR')
        self.assertEqual(tokens[0][1], 'hello')

    def test_single_quote_string(self):
        """单引号字符串也应被去掉"""
        tokens = Lexer("'world'").tokens
        self.assertEqual(tokens[0][1], 'world')

    def test_pipe_token(self):
        """管道符 | 应被正确识别"""
        tokens = Lexer("a | b").tokens
        self.assertEqual(tokens[1][0], 'PIPE')

    def test_safe_dot_token(self):
        """?. 应被识别为 SAFE_DOT"""
        tokens = Lexer("a?.b").tokens
        self.assertEqual(tokens[1][0], 'SAFE_DOT')

    def test_negative_number(self):
        """负数应被正确识别"""
        tokens = Lexer("[-1]").tokens
        self.assertEqual(tokens[1][1], -1)

    def test_position_tracking(self):
        """每个 token 应记录源码位置"""
        tokens = Lexer("users[0].name").tokens
        # 'users' 从位置 0 开始, '[' 从位置 5, '0' 从位置 6...
        self.assertEqual(tokens[0][2], 0)   # users
        self.assertEqual(tokens[1][2], 5)   # [
        self.assertEqual(tokens[2][2], 6)   # 0
        self.assertEqual(tokens[3][2], 7)   # ]
        self.assertEqual(tokens[4][2], 8)   # .
        self.assertEqual(tokens[5][2], 9)   # name

    def test_illegal_char_raises_syntax_error(self):
        """非法字符应抛出 DSLSyntaxError"""
        with self.assertRaises(DSLSyntaxError):
            Lexer("abc#def")

    def test_logic_operators(self):
        """and / or / && / || 应被识别为 LOGIC"""
        for op in ['and', 'or']:
            tokens = Lexer(f"a {op} b").tokens
            self.assertEqual(tokens[1][0], 'LOGIC')

    def test_func_ops(self):
        """contains / startsWith 应被识别为 FUNC_OP"""
        tokens = Lexer('name contains "A"').tokens
        self.assertEqual(tokens[1][0], 'FUNC_OP')
        self.assertEqual(tokens[1][1], 'contains')


# ──────────────────────────────────────────
# Parser 单元测试
# ──────────────────────────────────────────

class TestParser(unittest.TestCase):

    def _parse(self, query: str) -> Query:
        lexer = Lexer(query)
        return Parser(lexer.tokens, source=query).parse()

    def test_simple_path_ast(self):
        """users.name => Query -> Path -> [GetField, GetField]"""
        ast = self._parse("users.name")
        self.assertIsInstance(ast, Query)
        self.assertEqual(len(ast.stages), 1)
        path = ast.stages[0]
        self.assertIsInstance(path, Path)
        self.assertEqual(len(path.steps), 2)
        self.assertIsInstance(path.steps[0], GetField)
        self.assertEqual(path.steps[0].name, 'users')
        self.assertEqual(path.steps[1].name, 'name')

    def test_index_access_ast(self):
        """users[0] => Path -> [GetField, IndexAccess(0)]"""
        ast = self._parse("users[0]")
        path = ast.stages[0]
        self.assertIsInstance(path.steps[1], IndexAccess)
        self.assertEqual(path.steps[1].index, 0)

    def test_filter_ast(self):
        """users[age > 25] => Path -> [GetField, Filter(BinOp)]"""
        ast = self._parse("users[age > 25]")
        path = ast.stages[0]
        filt = path.steps[1]
        self.assertIsInstance(filt, Filter)
        cond = filt.condition
        self.assertIsInstance(cond, BinOp)
        self.assertEqual(cond.op, '>')
        self.assertIsInstance(cond.left, Ident)
        self.assertEqual(cond.left.name, 'age')
        self.assertIsInstance(cond.right, Literal)
        self.assertEqual(cond.right.value, 25)

    def test_pipeline_ast(self):
        """users | sort(age) => Query -> [Path, FuncCall]"""
        ast = self._parse("users | sort(age)")
        self.assertEqual(len(ast.stages), 2)
        self.assertIsInstance(ast.stages[0], Path)
        self.assertIsInstance(ast.stages[1], FuncCall)
        self.assertEqual(ast.stages[1].name, 'sort')
        self.assertEqual(len(ast.stages[1].args), 1)

    def test_safe_nav_ast(self):
        """a?.b => Path -> [GetField(safe=False), GetField(safe=True)]"""
        ast = self._parse("a?.b")
        path = ast.stages[0]
        self.assertFalse(path.steps[0].safe)
        self.assertTrue(path.steps[1].safe)

    def test_and_or_precedence(self):
        """a == 1 or b == 2 and c == 3 => or(a==1, and(b==2, c==3))"""
        ast = self._parse("x[a == 1 or b == 2 and c == 3]")
        filt = ast.stages[0].steps[1]
        cond = filt.condition
        self.assertIsInstance(cond, BinOp)
        self.assertEqual(cond.op, 'or')
        self.assertIsInstance(cond.right, BinOp)
        self.assertEqual(cond.right.op, 'and')

    def test_multi_func_args(self):
        """func(a, 1, "x") => FuncCall with 3 args"""
        ast = self._parse('x | func(a, 1, "hello")')
        func = ast.stages[1]
        self.assertIsInstance(func, FuncCall)
        self.assertEqual(len(func.args), 3)
        self.assertIsInstance(func.args[0], Ident)
        self.assertIsInstance(func.args[1], Literal)
        self.assertIsInstance(func.args[2], Literal)
        self.assertEqual(func.args[2].value, 'hello')


# ──────────────────────────────────────────
# Evaluator 单元测试（手动构造 AST）
# ──────────────────────────────────────────

class TestEvaluator(unittest.TestCase):

    def setUp(self):
        self.evaluator = DSLEvaluator()

    def test_getfield_on_dict(self):
        """GetField 从 dict 中取值"""
        node = Path([GetField("x")])
        res = self.evaluator.evaluate(Query([node]), {"x": 42})
        self.assertEqual(res, 42)

    def test_getfield_on_list_maps(self):
        """GetField 遇到 list 应自动映射"""
        node = Path([GetField("items"), GetField("v")])
        data = {"items": [{"v": 1}, {"v": 2}, {"v": 3}]}
        res = self.evaluator.evaluate(Query([node]), data)
        self.assertEqual(res, [1, 2, 3])

    def test_index_access(self):
        """IndexAccess 取指定索引"""
        node = Path([GetField("arr"), IndexAccess(1)])
        res = self.evaluator.evaluate(Query([node]), {"arr": [10, 20, 30]})
        self.assertEqual(res, 20)

    def test_filter_evaluates_condition(self):
        """Filter 应根据条件筛选"""
        cond = BinOp(Ident("v"), ">", Literal(5))
        node = Path([GetField("arr"), Filter(cond), GetField("v")])
        data = {"arr": [{"v": 3}, {"v": 7}, {"v": 10}]}
        res = self.evaluator.evaluate(Query([node]), data)
        self.assertEqual(res, [7, 10])

    def test_safe_getfield_on_none(self):
        """safe GetField 遇到 None 返回 None 而非崩溃"""
        node = Path([GetField("x"), GetField("y", safe=True)])
        res = self.evaluator.evaluate(Query([node]), {"x": None})
        self.assertIsNone(res)


if __name__ == '__main__':
    unittest.main()
