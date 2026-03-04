#!/usr/bin/env python3
"""
性能基准测试
============
生成 N 条用户数据，测量各种查询的执行耗时。
用法: python benchmark.py [--size 1000]
"""

import argparse
import json
import random
import string
import sys
import os
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from json_dsl import DSLEvaluator, Ident, Literal


def generate_data(n: int) -> Dict[str, Any]:
    """生成 n 条随机用户数据"""
    random.seed(42)
    names = ['Alice', 'Bob', 'Cindy', 'David', 'Eve', 'Frank', 'Grace',
             'Henry', 'Ivy', 'Jack', 'Kate', 'Leo', 'Mia', 'Noah', 'Olivia']
    domains = ['gmail.com', 'test.com', 'example.org', 'bytedance.com']

    users = []
    for i in range(n):
        name = random.choice(names) + str(i)
        user: Dict[str, Any] = {
            "name": name,
            "age": random.randint(18, 65),
            "active": random.choice([True, False]),
            "score": round(random.uniform(0, 100), 2),
            "department": random.choice(["engineering", "product", "design", "marketing"]),
        }
        if random.random() > 0.2:
            user["profile"] = {"email": f"{name.lower()}@{random.choice(domains)}"}
        else:
            user["profile"] = None
        users.append(user)
    return {"users": users}


def create_evaluator() -> DSLEvaluator:
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


def benchmark(evaluator: DSLEvaluator, query: str, data: dict, runs: int = 100) -> float:
    """执行多次查询并返回平均耗时 (ms)"""
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        evaluator.execute(query, data)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    return sum(times) / len(times)


def main() -> None:
    parser = argparse.ArgumentParser(description='JSON DSL 性能基准测试')
    parser.add_argument('--size', type=int, default=1000, help='数据条数 (默认 1000)')
    parser.add_argument('--runs', type=int, default=100, help='每个查询执行次数 (默认 100)')
    args = parser.parse_args()

    n = args.size
    runs = args.runs
    data = generate_data(n)
    evaluator = create_evaluator()

    print(f"╔══════════════════════════════════════════════════════════════╗")
    print(f"║  JSON DSL 性能基准测试                                     ║")
    print(f"║  数据量: {n} 条  |  每查询执行: {runs} 次取平均             ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print()

    queries = [
        ("简单路径取值",           "users[0].name"),
        ("数组映射",              "users.name"),
        ("条件过滤",              "users[age > 30].name"),
        ("布尔过滤",              "users[active == true].name"),
        ("复合条件 (and)",        "users[age > 25 and active == true].name"),
        ("复合条件 (or)",         "users[age < 20 or age > 60].name"),
        ("字符串 contains",       'users[name contains "Alice"].age'),
        ("字符串 startsWith",     'users[department startsWith "eng"].name'),
        ("管道: filter + sort",   "users[age > 30] | sort(age) | .name"),
        ("管道: filter + sort + take", "users[active == true] | sort(score) | take(10) | .name"),
        ("多级管道 (全量)",        "users | sort(age) | reverse() | take(5) | .name"),
    ]

    print(f"{'查询场景':<26} {'查询表达式':<55} {'平均耗时':>10}")
    print("─" * 95)

    for label, query in queries:
        avg_ms = benchmark(evaluator, query, data, runs)
        print(f"  {label:<24} {query:<55} {avg_ms:>8.3f} ms")

    print("─" * 95)
    print()

    # 可扩展性测试: 不同数据规模
    print("可扩展性测试 (查询: users[age > 30].name)")
    print(f"{'数据量':>10} {'平均耗时':>12} {'吞吐量':>15}")
    print("─" * 40)
    for scale in [100, 500, 1000, 5000, 10000]:
        scaled_data = generate_data(scale)
        avg = benchmark(evaluator, "users[age > 30].name", scaled_data, runs=50)
        qps = 1000 / avg if avg > 0 else float('inf')
        print(f"  {scale:>8}   {avg:>9.3f} ms   {qps:>10.0f} qps")
    print()


if __name__ == '__main__':
    main()
