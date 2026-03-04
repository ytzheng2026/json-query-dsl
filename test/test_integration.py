"""
集成测试：CLI 端到端流程
========================
测试 main.py 的完整链路：文件读取 → 查询执行 → JSON 输出。
"""

import json
import os
import subprocess
import sys
import unittest

PROJECT_DIR = os.path.join(os.path.dirname(__file__), '..')
MAIN_PY = os.path.join(PROJECT_DIR, 'main.py')
INPUT_JSON = os.path.join(PROJECT_DIR, 'input.json')


class TestCLI(unittest.TestCase):

    def _run(self, args: list, stdin_data: str = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, MAIN_PY] + args,
            capture_output=True, text=True, cwd=PROJECT_DIR,
            input=stdin_data,
        )

    # ── 正常查询 ──

    def test_basic_query(self):
        """基本查询应返回 JSON 数组"""
        result = self._run(['-d', INPUT_JSON, '-q', 'users[age>25].name'])
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertIsInstance(data, list)
        self.assertTrue(len(data) > 0)

    def test_single_value_query(self):
        """单值查询应返回字符串"""
        result = self._run(['-d', INPUT_JSON, '-q', 'users[0].name'])
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertIsInstance(data, str)

    def test_compact_output(self):
        """--compact 应产生无缩进的单行输出"""
        result = self._run(['-d', INPUT_JSON, '-q', 'users.name', '--compact'])
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.strip().split('\n')
        self.assertEqual(len(lines), 1)

    def test_pipeline_query(self):
        """管道查询应正常工作"""
        result = self._run(['-d', INPUT_JSON, '-q', 'users | sort(age) | take(2) | .name'])
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(len(data), 2)

    # ── stdin 输入 ──

    def test_stdin_input(self):
        """通过 stdin 传入 JSON 数据"""
        json_input = '{"items": [1, 2, 3]}'
        result = self._run(['-q', 'items[0]'], stdin_data=json_input)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), 1)

    # ── 错误处理 ──

    def test_missing_file(self):
        """不存在的文件应返回退出码 1"""
        result = self._run(['-d', 'nonexistent.json', '-q', 'x'])
        self.assertEqual(result.returncode, 1)
        self.assertIn('不存在', result.stderr)

    def test_invalid_query_syntax(self):
        """语法错误应返回退出码 1 和友好错误"""
        result = self._run(['-d', INPUT_JSON, '-q', 'users[0]#name'])
        self.assertEqual(result.returncode, 1)
        self.assertIn('^', result.stderr)  # 应有位置指示符

    def test_missing_query_arg(self):
        """缺少 -q 参数应报错"""
        result = self._run(['-d', INPUT_JSON])
        self.assertNotEqual(result.returncode, 0)

    def test_unknown_function_error(self):
        """调用未知函数应返回退出码 1"""
        result = self._run(['-d', INPUT_JSON, '-q', 'users | nonexist()'])
        self.assertEqual(result.returncode, 1)
        self.assertIn('nonexist', result.stderr)


if __name__ == '__main__':
    unittest.main()
