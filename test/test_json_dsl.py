"""
JSON 查询 DSL 测试套件
======================
覆盖以下场景：
  1. 简单路径取值           2. 数组映射
  3. 条件过滤               4. 布尔过滤
  5. 复合条件 (and)         6. 管道 + 自定义函数
  7. contains 操作          8. startsWith 操作
  9. 安全导航 (?.)          10. 严格空引用异常
  11. 自定义函数 reverse
"""

import sys
import os
import unittest

# 将 src 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from json_dsl import DSLEvaluator, Ident, Literal, DSLSyntaxError, DSLRuntimeError


class TestJSONDSL(unittest.TestCase):

    def setUp(self):
        self.evaluator = DSLEvaluator()
        self.evaluator.register_function('sort', self._func_sort)
        self.evaluator.register_function('take', self._func_take)
        self.evaluator.register_function('reverse', self._func_reverse)

        # 从分离的 JSON 文件中读取测试数据
        data_path = os.path.join(os.path.dirname(__file__), 'test_data.json')
        with open(data_path, 'r', encoding='utf-8') as f:
            import json
            self.data = json.load(f)

    # ── 自定义管道函数 ──

    def _func_sort(self, data, args):
        field = args[0].name if isinstance(args[0], Ident) else str(args[0].value)
        return sorted(data, key=lambda x: x.get(field, 0))

    def _func_take(self, data, args):
        n = args[0].value if isinstance(args[0], Literal) else 0
        return data[:n]

    def _func_reverse(self, data, args):
        return list(reversed(data))

    # ── 测试用例 ──

    def test_01_simple_path(self):
        """路径取值：users[0].name => 'Alice'"""
        res = self.evaluator.execute("users[0].name", self.data)
        self.assertEqual(res, "Alice")

    def test_02_array_mapping(self):
        """数组映射：users.active => [True, False, True]"""
        res = self.evaluator.execute("users.active", self.data)
        self.assertEqual(res, [True, False, True])

    def test_03_simple_filter(self):
        """条件过滤：users[age > 25].name => ['Bob', 'Cindy']"""
        res = self.evaluator.execute("users[age > 25].name", self.data)
        self.assertEqual(res, ["Bob", "Cindy"])

    def test_04_bool_filter(self):
        """布尔过滤：users[active == true].age => [20, 28]"""
        res = self.evaluator.execute("users[active == true].age", self.data)
        self.assertEqual(res, [20, 28])

    def test_05_complex_filter_and(self):
        """复合 and 过滤：users[age >= 20 and active == true].name => ['Alice', 'Cindy']"""
        res = self.evaluator.execute("users[age >= 20 and active == true].name", self.data)
        self.assertEqual(res, ["Alice", "Cindy"])

    def test_06_pipeline_and_funcs(self):
        """管道 + 函数：users[age > 20] | sort(age) | take(1) | .name => ['Cindy']"""
        res = self.evaluator.execute("users[age > 20] | sort(age) | take(1) | .name", self.data)
        self.assertEqual(res, ["Cindy"])

    def test_07_contains(self):
        """contains：users[name contains "A"].name => ['Alice']"""
        res = self.evaluator.execute('users[name contains "A"].name', self.data)
        self.assertEqual(res, ["Alice"])

    def test_08_startswith(self):
        """startsWith：users[name startsWith "B"].age => [30]"""
        res = self.evaluator.execute('users[name startsWith "B"].age', self.data)
        self.assertEqual(res, [30])

    def test_09_safe_navigation(self):
        """安全导航：users[0]?.profile?.email => 'alice@test.com'，null 时不报错"""
        res = self.evaluator.execute("users[0]?.profile?.email", self.data)
        self.assertEqual(res, "alice@test.com")
        res_null = self.evaluator.execute("users[2]?.profile?.email", self.data)
        self.assertIsNone(res_null)

    def test_10_strict_null_error(self):
        """非安全导航遇到 null 应抛出 TypeError"""
        with self.assertRaises(DSLRuntimeError):
            self.evaluator.execute("users[1].profile.email", self.data)

    def test_11_custom_function_reverse(self):
        """自定义函数 reverse：users | reverse() | .name => ['Cindy', 'Bob', 'Alice']"""
        res = self.evaluator.execute("users | reverse() | .name", self.data)
        self.assertEqual(res, ["Cindy", "Bob", "Alice"])

    # ──────────────────────────────────────────
    # 回归测试：边界条件与更多场景
    # ──────────────────────────────────────────

    def test_12_index_out_of_bounds_strict(self):
        """越界索引后非安全取字段应抛 TypeError"""
        with self.assertRaises(DSLRuntimeError):
            self.evaluator.execute("users[99].name", self.data)

    def test_12b_index_out_of_bounds_safe(self):
        """越界索引后安全导航应返回 None"""
        res = self.evaluator.execute("users[99]?.name", self.data)
        self.assertIsNone(res)

    def test_13_filter_no_match(self):
        """过滤无匹配项应返回空数组"""
        res = self.evaluator.execute("users[age > 100].name", self.data)
        self.assertEqual(res, [])

    def test_14_nested_field(self):
        """嵌套对象取值：users[0].profile.email"""
        res = self.evaluator.execute("users[0].profile.email", self.data)
        self.assertEqual(res, "alice@test.com")

    def test_15_missing_field_returns_none(self):
        """访问不存在的字段返回 None"""
        res = self.evaluator.execute("users[0].nonexistent", self.data)
        self.assertIsNone(res)

    def test_16_not_equal_operator(self):
        """!= 操作符：users[active != true].name => ['Bob']"""
        res = self.evaluator.execute("users[active != true].name", self.data)
        self.assertEqual(res, ["Bob"])

    def test_17_less_than_operator(self):
        """< 操作符：users[age < 25].name => ['Alice']"""
        res = self.evaluator.execute("users[age < 25].name", self.data)
        self.assertEqual(res, ["Alice"])

    def test_18_less_equal_operator(self):
        """<= 操作符：users[age <= 28].name => ['Alice', 'Cindy']"""
        res = self.evaluator.execute("users[age <= 28].name", self.data)
        self.assertEqual(res, ["Alice", "Cindy"])

    def test_19_or_logic(self):
        """or 逻辑：users[age < 21 or age > 29].name => ['Alice', 'Bob']"""
        res = self.evaluator.execute("users[age < 21 or age > 29].name", self.data)
        self.assertEqual(res, ["Alice", "Bob"])

    def test_20_array_mapping_name(self):
        """数组映射取 name：users.name => ['Alice', 'Bob', 'Cindy']"""
        res = self.evaluator.execute("users.name", self.data)
        self.assertEqual(res, ["Alice", "Bob", "Cindy"])

    def test_21_array_mapping_age(self):
        """数组映射取 age：users.age => [20, 30, 28]"""
        res = self.evaluator.execute("users.age", self.data)
        self.assertEqual(res, [20, 30, 28])

    def test_22_chained_pipeline(self):
        """多级管道：users | sort(age) | reverse() | take(2) | .name"""
        res = self.evaluator.execute("users | sort(age) | reverse() | take(2) | .name", self.data)
        self.assertEqual(res, ["Bob", "Cindy"])

    def test_23_filter_then_index(self):
        """过滤后索引：users[active == true][1].name => 'Cindy'"""
        res = self.evaluator.execute("users[active == true][1].name", self.data)
        self.assertEqual(res, "Cindy")

    def test_24_safe_nav_on_missing_key(self):
        """安全导航在 Bob (无 profile 键) 上不抛异常"""
        res = self.evaluator.execute("users[1]?.profile?.email", self.data)
        self.assertIsNone(res)

    def test_25_empty_array_filter(self):
        """空数组上的过滤应返回空"""
        data = {"items": []}
        res = self.evaluator.execute("items[age > 1].name", data)
        self.assertEqual(res, [])

    def test_26_string_equality_filter(self):
        """字符串精确匹配过滤"""
        res = self.evaluator.execute('users[name == "Bob"].age', self.data)
        self.assertEqual(res, [30])

    def test_27_deeply_nested(self):
        """多层嵌套对象访问"""
        data = {"a": {"b": {"c": {"d": 42}}}}
        res = self.evaluator.execute("a.b.c.d", data)
        self.assertEqual(res, 42)

    def test_28_lexer_error(self):
        """非法字符应抛出 ValueError"""
        with self.assertRaises(DSLSyntaxError):
            self.evaluator.execute("users[0]#name", self.data)

    def test_29_unknown_function_error(self):
        """调用未注册函数应抛出 ValueError"""
        with self.assertRaises(DSLRuntimeError):
            self.evaluator.execute("users | unknown_fn()", self.data)

    def test_30_contains_no_match(self):
        """contains 无匹配"""
        res = self.evaluator.execute('users[name contains "Z"].name', self.data)
        self.assertEqual(res, [])

    def test_31_negative_index(self):
        """负索引取最后一个元素"""
        res = self.evaluator.execute("users[-1].name", self.data)
        self.assertEqual(res, "Cindy")

    def test_32_filter_and_or_combined(self):
        """and + or 组合：(age < 21 or age > 29) and active == true"""
        res = self.evaluator.execute(
            "users[(age < 21 or age > 29) and active == true].name", self.data
        )
        self.assertEqual(res, ["Alice"])


if __name__ == '__main__':
    unittest.main()
