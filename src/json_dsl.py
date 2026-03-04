"""
JSON 查询 DSL 实现
==================
本模块实现了一个轻量级的 JSON 查询 DSL（领域特定语言），
由三部分组成：词法分析器(Lexer)、语法分析器(Parser)、求值器(DSLEvaluator)。

用法示例：
    evaluator = DSLEvaluator()
    result = evaluator.execute("users[age > 25].name", data)
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


# ──────────────────────────────────────────
# AST 节点定义
# ──────────────────────────────────────────

class ASTNode:
    """所有 AST 节点的基类"""
    pass


class Query(ASTNode):
    """整体查询，包含多个管道阶段 (stages)"""
    def __init__(self, stages: List[ASTNode]) -> None:
        self.stages: List[ASTNode] = stages


class Path(ASTNode):
    """连续的属性获取路径，如 a.b.c"""
    def __init__(self, steps: List[ASTNode]) -> None:
        self.steps: List[ASTNode] = steps


class GetField(ASTNode):
    """对象属性读取，safe=True 表示安全导航 (?.)"""
    def __init__(self, name: str, safe: bool = False) -> None:
        self.name: str = name
        self.safe: bool = safe


class IndexAccess(ASTNode):
    """数组索引读取，如 [0]"""
    def __init__(self, index: int) -> None:
        self.index: int = index


class Filter(ASTNode):
    """带有条件的数组过滤操作，如 [age > 25]"""
    def __init__(self, condition: ASTNode) -> None:
        self.condition: ASTNode = condition


class FuncCall(ASTNode):
    """函数调用，如 sort(age)"""
    def __init__(self, name: str, args: List[ASTNode]) -> None:
        self.name: str = name
        self.args: List[ASTNode] = args


class BinOp(ASTNode):
    """二元操作符运算，如 age > 25"""
    def __init__(self, left: ASTNode, op: str, right: ASTNode) -> None:
        self.left: ASTNode = left
        self.op: str = op
        self.right: ASTNode = right


class Literal(ASTNode):
    """字面量：数字、字符串、布尔、null"""
    def __init__(self, value: Union[int, str, bool, None]) -> None:
        self.value: Union[int, str, bool, None] = value


class Ident(ASTNode):
    """标识符引用，如 age, name"""
    def __init__(self, name: str) -> None:
        self.name: str = name


# 类型别名
Token = Tuple[str, Any, int]  # (类型, 值, 源码位置)
JSONValue = Union[Dict[str, Any], List[Any], str, int, float, bool, None]


# ──────────────────────────────────────────
# 友好错误信息
# ──────────────────────────────────────────

class DSLSyntaxError(Exception):
    """带有源码位置指示的语法错误"""
    def __init__(self, message: str, source: str, pos: int) -> None:
        self.source: str = source
        self.pos: int = pos
        pointer = ' ' * pos + '^'
        full_msg = f"{message}\n  {source}\n  {pointer}"
        super().__init__(full_msg)


class DSLRuntimeError(Exception):
    """运行时错误（空引用等）"""
    def __init__(self, message: str, source: str = '', pos: int = -1) -> None:
        if source and pos >= 0:
            pointer = ' ' * pos + '^'
            full_msg = f"{message}\n  {source}\n  {pointer}"
        else:
            full_msg = message
        super().__init__(full_msg)


# ──────────────────────────────────────────
# 词法分析器 (Lexer)
# ──────────────────────────────────────────

class Lexer:
    """将查询字符串拆分为 Token 列表（同时记录每个 Token 的源码位置）"""

    def __init__(self, text: str) -> None:
        self.text: str = text
        self.pos: int = 0
        self.tokens: List[Token] = []
        self.tokenize()

    def tokenize(self) -> None:
        pattern = re.compile(r"""
            (?P<SPACE>\s+) |
            (?P<SAFE_DOT>\?\.) |
            (?P<DOT>\.) |
            (?P<LBRACK>\[) |
            (?P<RBRACK>\]) |
            (?P<PIPE>\|) |
            (?P<LPAREN>\() |
            (?P<RPAREN>\)) |
            (?P<COMMA>,) |
            (?P<OP>==|!=|>=|<=|>|<) |
            (?P<LOGIC>&&|\|\||and\b|or\b) |
            (?P<FUNC_OP>contains\b|startsWith\b) |
            (?P<BOOL>true\b|false\b) |
            (?P<NULL>null\b) |
            (?P<ID>[a-zA-Z_]\w*) |
            (?P<NUM>-?\d+) |
            (?P<STR>"[^"]*"|'[^']*')
        """, re.VERBOSE)

        pos: int = 0
        text: str = self.text
        while pos < len(text):
            match = pattern.match(text, pos)
            if not match:
                raise DSLSyntaxError(
                    f"Unexpected character '{text[pos]}'",
                    source=text, pos=pos
                )
            kind: str = match.lastgroup  # type: ignore[assignment]
            value: Any = match.group(kind)
            token_pos: int = match.start()
            if kind != 'SPACE':
                if kind == 'STR':     value = value[1:-1]
                elif kind == 'NUM':   value = int(value)
                elif kind == 'BOOL':  value = (value == 'true')
                elif kind == 'NULL':  value = None
                self.tokens.append((kind, value, token_pos))
            pos = match.end()


# ──────────────────────────────────────────
# 语法分析器 (Parser) — 递归下降
# ──────────────────────────────────────────

class Parser:
    """将 Token 列表解析为 AST (抽象语法树)"""

    def __init__(self, tokens: List[Token], source: str = '') -> None:
        self.tokens: List[Token] = tokens
        self.source: str = source
        self.pos: int = 0

    def _token_pos(self) -> int:
        """获取当前 token 的源码位置"""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos][2]
        return len(self.source)

    def peek(self, offset: int = 0) -> Optional[Token]:
        if self.pos + offset < len(self.tokens):
            return self.tokens[self.pos + offset]
        return None

    def consume(self, expected_type: Optional[str] = None) -> Token:
        tok = self.peek()
        if not tok:
            raise DSLSyntaxError(
                f"Expected {expected_type}, got end of query",
                source=self.source, pos=len(self.source)
            )
        if expected_type and tok[0] != expected_type:
            raise DSLSyntaxError(
                f"Expected {expected_type}, got '{tok[1]}'",
                source=self.source, pos=tok[2]
            )
        self.pos += 1
        return tok

    # ── 顶层：管道表达式 ──

    def parse(self) -> Query:
        stages: List[ASTNode] = [self.parse_stage()]
        while self.peek() and self.peek()[0] == 'PIPE':  # type: ignore[index]
            self.consume('PIPE')
            stages.append(self.parse_stage())
        return Query(stages)

    def parse_stage(self) -> ASTNode:
        tok = self.peek()
        if tok and tok[0] == 'ID' and self.peek(1) and self.peek(1)[0] == 'LPAREN':  # type: ignore[index]
            return self.parse_func_call()
        return self.parse_path()

    def parse_func_call(self) -> FuncCall:
        name: str = self.consume('ID')[1]
        self.consume('LPAREN')
        args: List[ASTNode] = []
        if self.peek() and self.peek()[0] != 'RPAREN':  # type: ignore[index]
            args.append(self.parse_expr())
            while self.peek() and self.peek()[0] == 'COMMA':  # type: ignore[index]
                self.consume('COMMA')
                args.append(self.parse_expr())
        self.consume('RPAREN')
        return FuncCall(name, args)

    # ── 路径解析 ──

    def parse_path(self) -> Path:
        steps: List[ASTNode] = []
        if self.peek() and self.peek()[0] == 'DOT':  # type: ignore[index]
            self.consume('DOT')
            name: str = self.consume('ID')[1]
            steps.append(GetField(name, safe=False))
        elif self.peek() and self.peek()[0] == 'SAFE_DOT':  # type: ignore[index]
            self.consume('SAFE_DOT')
            name = self.consume('ID')[1]
            steps.append(GetField(name, safe=True))
        elif self.peek() and self.peek()[0] == 'ID':  # type: ignore[index]
            name = self.consume('ID')[1]
            steps.append(GetField(name, safe=False))
        else:
            raise DSLSyntaxError(
                f"Unexpected token '{self.peek()[1] if self.peek() else 'EOF'}'",
                source=self.source, pos=self._token_pos()
            )

        while self.peek():
            tok = self.peek()
            assert tok is not None
            if tok[0] == 'LBRACK':
                self.consume('LBRACK')
                if (self.peek() and self.peek()[0] == 'NUM'  # type: ignore[index]
                        and (self.peek(1) is None or self.peek(1)[0] == 'RBRACK')):  # type: ignore[index]
                    idx: int = self.consume('NUM')[1]
                    steps.append(IndexAccess(idx))
                else:
                    cond: ASTNode = self.parse_expr()
                    steps.append(Filter(cond))
                self.consume('RBRACK')
            elif tok[0] == 'DOT':
                self.consume('DOT')
                name = self.consume('ID')[1]
                steps.append(GetField(name, safe=False))
            elif tok[0] == 'SAFE_DOT':
                self.consume('SAFE_DOT')
                name = self.consume('ID')[1]
                steps.append(GetField(name, safe=True))
            else:
                break
        return Path(steps)

    # ── 表达式解析（用于 Filter 条件） ──

    def parse_expr(self) -> ASTNode:
        node: ASTNode = self.parse_and()
        while self.peek() and self.peek()[0] == 'LOGIC' and self.peek()[1] in ('or', '||'):  # type: ignore[index]
            op: str = self.consume()[1]
            node = BinOp(node, op, self.parse_and())
        return node

    def parse_and(self) -> ASTNode:
        node: ASTNode = self.parse_comp()
        while self.peek() and self.peek()[0] == 'LOGIC' and self.peek()[1] in ('and', '&&'):  # type: ignore[index]
            op: str = self.consume()[1]
            node = BinOp(node, op, self.parse_comp())
        return node

    def parse_comp(self) -> ASTNode:
        left: ASTNode = self.parse_primary()
        if self.peek() and self.peek()[0] in ('OP', 'FUNC_OP'):  # type: ignore[index]
            op: str = self.consume()[1]
            right: ASTNode = self.parse_primary()
            return BinOp(left, op, right)
        return left

    def parse_primary(self) -> ASTNode:
        tok: Token = self.consume()
        if tok[0] == 'LPAREN':
            node: ASTNode = self.parse_expr()
            self.consume('RPAREN')
            return node
        elif tok[0] in ('STR', 'NUM', 'BOOL', 'NULL'):
            return Literal(tok[1])
        elif tok[0] == 'ID':
            return Ident(tok[1])
        raise DSLSyntaxError(
            f"Unexpected token '{tok[1]}' in expression",
            source=self.source, pos=tok[2]
        )


# ──────────────────────────────────────────
# 求值器 (DSLEvaluator)
# ──────────────────────────────────────────

class DSLEvaluator:
    """遍历 AST 并在 JSON 数据上执行查询"""

    def __init__(self) -> None:
        self.custom_functions: Dict[str, Callable[..., Any]] = {}

    def register_function(self, name: str, func: Callable[..., Any]) -> None:
        """注册自定义管道函数，签名为 func(data, args)"""
        self.custom_functions[name] = func

    def execute(self, query: str, data: JSONValue) -> JSONValue:
        """执行一条 DSL 查询并返回结果"""
        self._current_query = query
        lexer = Lexer(query)
        parser = Parser(lexer.tokens, source=query)
        ast = parser.parse()
        return self.evaluate(ast, data)

    def evaluate(self, node: ASTNode, data: JSONValue) -> JSONValue:
        if isinstance(node, Query):
            res: JSONValue = data
            for stage in node.stages:
                res = self.evaluate(stage, res)
            return res
        elif isinstance(node, Path):
            res = data
            for step in node.steps:
                res = self._evaluate_step(step, res)
            return res
        elif isinstance(node, FuncCall):
            func = self.custom_functions.get(node.name)
            if not func:
                raise DSLRuntimeError(f"Unknown function '{node.name}'. Available: {list(self.custom_functions.keys())}")
            return func(data, node.args)
        return None

    def _evaluate_step(self, step: ASTNode, data: JSONValue) -> JSONValue:
        if data is None:
            if isinstance(step, GetField) and step.safe:
                return None
            raise DSLRuntimeError("Cannot access property on null value. Use '?.' for safe navigation")

        if isinstance(step, GetField):
            if isinstance(data, list):
                res: List[Any] = []
                for item in data:
                    if item is None:
                        if step.safe:
                            res.append(None)
                        else:
                            raise DSLRuntimeError("Null element in array during mapping. Use '?.' for safe navigation")
                    elif isinstance(item, dict):
                        res.append(item.get(step.name))
                    else:
                        if step.safe:
                            res.append(None)
                        else:
                            raise DSLRuntimeError(f"Expected dict, got {type(item).__name__}")
                return res
            elif isinstance(data, dict):
                return data.get(step.name)
            else:
                if step.safe:
                    return None
                raise DSLRuntimeError(f"Cannot get field '{step.name}' on {type(data).__name__}")

        elif isinstance(step, IndexAccess):
            if isinstance(data, list):
                try:
                    return data[step.index]
                except IndexError:
                    return None
            return None

        elif isinstance(step, Filter):
            if isinstance(data, list):
                return [item for item in data if self.evaluate_cond(step.condition, item)]
            return data

        return None

    def evaluate_cond(self, node: ASTNode, data: JSONValue) -> Any:
        if isinstance(node, Literal):
            return node.value
        elif isinstance(node, Ident):
            if isinstance(data, dict):
                return data.get(node.name)
            return None
        elif isinstance(node, BinOp):
            left: Any = self.evaluate_cond(node.left, data)
            right: Any = self.evaluate_cond(node.right, data)
            op: str = node.op
            if op == '==':  return left == right
            if op == '!=':  return left != right
            try:
                if op == '>':   return left > right if (left is not None and right is not None) else False
                if op == '>=':  return left >= right if (left is not None and right is not None) else False
                if op == '<':   return left < right if (left is not None and right is not None) else False
                if op == '<=':  return left <= right if (left is not None and right is not None) else False
            except TypeError:
                return False  # 类型不兼容时（如 str > bool），返回 False
            if op in ('and', '&&'):  return bool(left and right)
            if op in ('or', '||'):   return bool(left or right)
            if op == 'contains':
                if isinstance(left, (str, list)):
                    return right in left
                return False
            if op == 'startsWith':
                if isinstance(left, str) and isinstance(right, str):
                    return left.startswith(right)
                return False
        return False
