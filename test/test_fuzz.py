"""
模糊测试 (Fuzz Testing)
========================
随机生成大量合法和非法查询，验证：
  - 合法查询不会抛出非预期异常（只允许 DSLSyntaxError / DSLRuntimeError）
  - 非法查询必须被优雅捕获，不允许出现 IndexError / KeyError 等内部错误
"""

import random
import string
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from json_dsl import DSLEvaluator, DSLSyntaxError, DSLRuntimeError, Ident, Literal


SAMPLE_DATA = {
    "users": [
        {"name": "Alice", "age": 20, "active": True},
        {"name": "Bob", "age": 30, "active": False},
        {"name": "Cindy", "age": 28, "active": True},
    ],
    "empty": [],
    "value": 42,
    "nested": {"a": {"b": {"c": 1}}},
}

# 合法查询模板（参数化生成）
VALID_FIELDS = ['name', 'age', 'active', 'nonexistent']
VALID_OPS = ['==', '!=', '>', '>=', '<', '<=']
VALID_VALUES = ['25', '30', '0', '-1', 'true', 'false', '"Alice"', '"X"']


def random_valid_query() -> str:
    """随机生成一个语法合法的查询"""
    templates = [
        lambda: f"users[{random.randint(0, 5)}].{random.choice(VALID_FIELDS)}",
        lambda: f"users.{random.choice(VALID_FIELDS)}",
        lambda: f"users[{random.choice(VALID_FIELDS)} {random.choice(VALID_OPS)} {random.choice(VALID_VALUES)}].{random.choice(VALID_FIELDS)}",
        lambda: f"users[{random.choice(VALID_FIELDS)} {random.choice(VALID_OPS)} {random.choice(VALID_VALUES)}]",
        lambda: f"nested.a.b.c",
        lambda: f"value",
        lambda: f"empty.name",
    ]
    return random.choice(templates)()


def random_garbage_query() -> str:
    """随机生成一个可能非法的查询"""
    generators = [
        lambda: ''.join(random.choices(string.ascii_letters + '[]().><=!|? ', k=random.randint(1, 30))),
        lambda: f"users[{''.join(random.choices('[]()><=!.', k=random.randint(1, 10)))}]",
        lambda: f"{'.' * random.randint(1, 5)}name",
        lambda: f"users | | .name",
        lambda: f"users[0][0][0][0][0]",
        lambda: f"users[age >> 25]",
        lambda: f"[[[",
        lambda: f"",
        lambda: f"   ",
        lambda: f"@#$%",
    ]
    return random.choice(generators)()


class TestFuzz(unittest.TestCase):

    def setUp(self):
        self.evaluator = DSLEvaluator()
        self.evaluator.register_function('sort', lambda d, a: sorted(d, key=lambda x: x.get(a[0].name, 0)) if isinstance(d, list) else d)
        self.evaluator.register_function('take', lambda d, a: d[:a[0].value] if isinstance(d, list) else d)
        self.evaluator.register_function('reverse', lambda d, a: list(reversed(d)) if isinstance(d, list) else d)

    def test_valid_queries_no_crash(self):
        """100 条随机合法查询不应抛出非预期异常"""
        random.seed(12345)
        for i in range(100):
            query = random_valid_query()
            try:
                self.evaluator.execute(query, SAMPLE_DATA)
            except (DSLSyntaxError, DSLRuntimeError):
                pass  # 这些是可预期的业务异常
            except Exception as e:
                self.fail(f"查询 #{i} '{query}' 抛出了非预期异常: {type(e).__name__}: {e}")

    def test_garbage_queries_no_internal_error(self):
        """200 条随机垃圾查询不应抛出 IndexError / KeyError 等内部错误"""
        random.seed(54321)
        allowed_exceptions = (DSLSyntaxError, DSLRuntimeError, ValueError, TypeError)
        for i in range(200):
            query = random_garbage_query()
            try:
                self.evaluator.execute(query, SAMPLE_DATA)
            except allowed_exceptions:
                pass  # 优雅报错
            except Exception as e:
                self.fail(
                    f"垃圾查询 #{i} '{query}' 抛出了内部异常: "
                    f"{type(e).__name__}: {e}"
                )

    def test_empty_and_whitespace_queries(self):
        """空查询和纯空白查询应被优雅处理"""
        for query in ['', '   ', '\t\n']:
            with self.assertRaises((DSLSyntaxError, ValueError)):
                self.evaluator.execute(query, SAMPLE_DATA)


if __name__ == '__main__':
    unittest.main()
