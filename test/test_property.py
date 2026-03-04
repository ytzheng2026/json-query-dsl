"""
属性测试 (Property-Based Testing)
==================================
验证查询结果的数学性质，例如：
  - 过滤结果一定是原数组的子集
  - 映射结果长度 == 原数组长度
  - take(n) 结果长度 <= n
  - sort 不改变元素集合

不依赖 hypothesis 库，手动实现属性验证。
"""

import random
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from json_dsl import DSLEvaluator, Ident, Literal


def generate_random_users(n: int) -> list:
    """生成 n 条随机用户数据"""
    random.seed(42)
    return [
        {
            "name": f"User{i}",
            "age": random.randint(10, 80),
            "active": random.choice([True, False]),
            "score": round(random.uniform(0, 100), 2),
        }
        for i in range(n)
    ]


class TestProperties(unittest.TestCase):

    def setUp(self):
        self.evaluator = DSLEvaluator()
        self.evaluator.register_function('sort', self._sort)
        self.evaluator.register_function('take', self._take)
        self.evaluator.register_function('reverse', self._reverse)
        self.evaluator.register_function('count', self._count)
        self.users = generate_random_users(200)
        self.data = {"users": self.users}

    def _sort(self, d, a):
        f = a[0].name if isinstance(a[0], Ident) else str(a[0].value)
        return sorted(d, key=lambda x: x.get(f, 0))

    def _take(self, d, a):
        return d[:a[0].value if isinstance(a[0], Literal) else 0]

    def _reverse(self, d, a):
        return list(reversed(d))

    def _count(self, d, a):
        return len(d)

    # ── 属性 1: 映射保持长度 ──

    def test_mapping_preserves_length(self):
        """users.name 的长度应 == users 数组长度"""
        result = self.evaluator.execute("users.name", self.data)
        self.assertEqual(len(result), len(self.users))

    def test_mapping_preserves_length_age(self):
        """users.age 的长度应 == users 数组长度"""
        result = self.evaluator.execute("users.age", self.data)
        self.assertEqual(len(result), len(self.users))

    # ── 属性 2: 过滤结果是子集 ──

    def test_filter_is_subset(self):
        """users[age > X] 的结果集一定是 users 的子集"""
        for threshold in [10, 25, 40, 60, 80]:
            result = self.evaluator.execute(
                f"users[age > {threshold}]", self.data
            )
            original_names = {u["name"] for u in self.users}
            filtered_names = {u["name"] for u in result}
            self.assertTrue(
                filtered_names.issubset(original_names),
                f"threshold={threshold}: 过滤结果不是原数组子集"
            )

    def test_filter_result_satisfies_condition(self):
        """users[age > 30] 的每个元素都应满足 age > 30"""
        result = self.evaluator.execute("users[age > 30]", self.data)
        for user in result:
            self.assertGreater(user["age"], 30, f"用户 {user['name']} 不满足 age > 30")

    def test_filter_active_condition(self):
        """users[active == true] 的每个元素都应满足 active == True"""
        result = self.evaluator.execute("users[active == true]", self.data)
        for user in result:
            self.assertTrue(user["active"], f"用户 {user['name']} 不满足 active == true")

    # ── 属性 3: take(n) 的长度 <= n ──

    def test_take_limits_length(self):
        """take(n) 结果长度 <= n"""
        for n in [1, 5, 10, 50, 300]:
            result = self.evaluator.execute(f"users | take({n})", self.data)
            self.assertLessEqual(
                len(result), n,
                f"take({n}) 返回了 {len(result)} 条"
            )

    def test_take_exact_when_enough(self):
        """当数据足够时，take(n) 应返回恰好 n 条"""
        result = self.evaluator.execute("users | take(5)", self.data)
        self.assertEqual(len(result), 5)

    # ── 属性 4: sort 不改变元素集合 ──

    def test_sort_preserves_elements(self):
        """sort 后的元素集合应和排序前完全一致"""
        original = self.evaluator.execute("users.name", self.data)
        sorted_result = self.evaluator.execute("users | sort(age) | .name", self.data)
        self.assertEqual(sorted(original), sorted(sorted_result))

    def test_sort_is_ordered(self):
        """sort(age) 后 age 应单调递增"""
        result = self.evaluator.execute("users | sort(age) | .age", self.data)
        for i in range(len(result) - 1):
            self.assertLessEqual(result[i], result[i + 1])

    # ── 属性 5: reverse 是自逆的 ──

    def test_reverse_is_involution(self):
        """reverse(reverse(x)) == x"""
        original = self.evaluator.execute("users.name", self.data)
        double_reversed = self.evaluator.execute(
            "users | reverse() | reverse() | .name", self.data
        )
        self.assertEqual(original, double_reversed)

    # ── 属性 6: filter + count 一致性 ──

    def test_filter_count_consistency(self):
        """过滤结果的个数应 <= 总数"""
        total = len(self.users)
        for threshold in [20, 40, 60]:
            result = self.evaluator.execute(
                f"users[age > {threshold}]", self.data
            )
            self.assertLessEqual(len(result), total)

    # ── 属性 7: 不同过滤阈值的单调性 ──

    def test_filter_monotonicity(self):
        """随着 threshold 增大，users[age > threshold] 的结果数应单调不增"""
        prev_count = len(self.users) + 1
        for threshold in range(10, 81, 5):
            result = self.evaluator.execute(
                f"users[age > {threshold}]", self.data
            )
            self.assertLessEqual(
                len(result), prev_count,
                f"threshold={threshold}: 结果数 {len(result)} > 上一轮 {prev_count}"
            )
            prev_count = len(result)


if __name__ == '__main__':
    unittest.main()
