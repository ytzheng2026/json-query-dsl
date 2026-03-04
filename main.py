#!/usr/bin/env python3
"""
JSON 查询 DSL 命令行工具
========================
用法：
  python main.py --data input.json --query 'users[age>25].name'
  python main.py -d input.json -q 'users.active'
  echo '{"a":1}' | python main.py -q 'a'
"""

import argparse
import json
import sys
import os

# 将 src 目录加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from json_dsl import DSLEvaluator, Ident, Literal, DSLSyntaxError, DSLRuntimeError


def create_default_evaluator() -> DSLEvaluator:
    """创建一个自带常用管道函数的求值器"""
    evaluator = DSLEvaluator()

    def func_sort(data: list, args: list) -> list:
        field = args[0].name if isinstance(args[0], Ident) else str(args[0].value)
        return sorted(data, key=lambda x: x.get(field, 0))

    def func_take(data: list, args: list) -> list:
        n = args[0].value if isinstance(args[0], Literal) else 0
        return data[:n]

    def func_reverse(data: list, args: list) -> list:
        return list(reversed(data))

    def func_count(data: list, args: list) -> int:
        return len(data)

    evaluator.register_function('sort', func_sort)
    evaluator.register_function('take', func_take)
    evaluator.register_function('reverse', func_reverse)
    evaluator.register_function('count', func_count)

    return evaluator


def main() -> None:
    parser = argparse.ArgumentParser(
        description='JSON 查询 DSL — 对 JSON 数据执行路径选择、过滤、投影',
        epilog='示例: python main.py -d input.json -q \'users[age>25].name\''
    )
    parser.add_argument('-d', '--data', type=str, help='JSON 数据文件路径')
    parser.add_argument('-q', '--query', type=str, required=True, help='DSL 查询表达式')
    parser.add_argument('--pretty', action='store_true', default=True, help='格式化输出 (默认开启)')
    parser.add_argument('--compact', action='store_true', help='紧凑输出')

    args = parser.parse_args()

    # 读取 JSON 数据
    if args.data:
        try:
            with open(args.data, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"错误: 文件 '{args.data}' 不存在", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"错误: JSON 解析失败 — {e}", file=sys.stderr)
            sys.exit(1)
    elif not sys.stdin.isatty():
        data = json.load(sys.stdin)
    else:
        print("错误: 请通过 --data 指定文件或通过 stdin 传入 JSON 数据", file=sys.stderr)
        sys.exit(1)

    # 执行查询
    evaluator = create_default_evaluator()
    try:
        result = evaluator.execute(args.query, data)
    except (DSLSyntaxError, DSLRuntimeError) as e:
        print(f"查询错误:\n{e}", file=sys.stderr)
        sys.exit(1)

    # 输出结果
    indent = None if args.compact else 2
    print(json.dumps(result, ensure_ascii=False, indent=indent))


if __name__ == '__main__':
    main()
