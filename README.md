# JSON 查询 DSL 实现

## 项目结构
```
json-query-dsl/
├── README.md              # 题目描述 + 实现思路
├── PROCESS.md             # 解题全过程记录
├── main.py                # CLI 命令行入口
├── benchmark.py           # 性能基准测试
├── Makefile               # test / lint / demo / report
├── input.json             # 示例 JSON 数据
├── test_report.txt        # 测试报告
├── .github/workflows/     # GitHub Actions CI
├── src/
│   ├── __init__.py        # 包导出
│   └── json_dsl.py        # 核心实现（Lexer + Parser + DSLEvaluator）
└── test/
    ├── __init__.py
    └── test_json_dsl.py   # 33 条测试用例
```

快速使用：
```bash
# 执行查询
python3 main.py -d input.json -q 'users[age>25].name'

# 管道 + 函数
python3 main.py -d input.json -q 'users[active==true] | sort(age) | take(3) | .name'

# 运行测试 / lint / demo
make test
make lint
make demo

# 性能基准测试
python3 benchmark.py --size 1000
```

## 任务描述
实现一个对 JSON 的查询 DSL (领域语言)，支持路径选择、数组过滤、投影，输出结果 JSON。

## MVP 要求
给定 JSON 文档 `input.json`，支持以下查询：
1. 路径：
   - `users[0].name`
   - `users.name`（表示对数组映射：取每个user的name）
2. 过滤：
   - `users[age > 25].name`
   - `users[active == true]`
3. 基本操作符：`== != > >= < <=`，以及 `and / or`（可选）

输出：
- 单值就输出值
- 多值输出数组

## 加分项
- 支持 `|` 管道：`users[age>25] | sort(age) | take(3) | .name`
- 支持 `contains / startsWith`
- 支持 `?` 安全导航：`users[0]?.profile?.email`
- 支持自定义函数（注册机制）

## 验收用例
输入：
```json
{
  "users": [
    {"name": "Alice", "age": 20, "active": true},
    {"name": "Bob", "age": 30, "active": false},
    {"name": "Cindy", "age": 28, "active": true}
  ]
}
```
查询：
- `users[age>25].name` => `["Bob", "Cindy"]`
- `users.active` => `[true, false, true]`
- `users[active==true].age` => `[20, 28]`

## 实现目标与方法原理

### 核心目标
将一段纯文本形式的 JSON 查询语句（如 `users[age>25].name`），转换并作用于实际的 JSON 数据（Python dict/list），最终得出期望的过滤、投影或计算结果。

### 实现步骤与关键代码结构

我们在 `json_dsl.py` 中，将自定义 DSL 的实现拆分为三个核心组件：**词法分析 (Lexer)**、**语法分析 (Parser)** 和 **求值器 (DSLEvaluator)**。

#### 1. 词法分析 `class Lexer`
**目标：** 将一长串文本查询打碎成一个个有意义的**词法单元 (Token)**。
- **具体实现：** 
  利用 `re.VERBOSE` 编写复杂的正则表达式定义合法的语法成分。
  ```python
  pattern = re.compile(r"""
      (?P<SPACE>\s+) |
      (?P<SAFE_DOT>\?\.) |
      (?P<DOT>\.) |
      (?P<LBRACK>\[) |
      (?P<RBRACK>\]) |
      (?P<PIPE>\|) |
      (?P<OP>==|!=|>=|<=|>|<) |
      # ... 等其他规则
  """, re.VERBOSE)
  ```
- **工作机制：** `tokenize()` 方法遍历输入字符串，不断匹配正则组。遇到字符串（`STR`）、数字（`NUM`）或布尔（`BOOL`）类型时，甚至会直接做类型转换（例如 `int("25")`）。
- **产出结果：** `self.tokens` 列表存储所有的标记。

**示例：** 对查询 `users[age>25].name` 进行词法分析后产出：
```
Tokens:
  ('ID',     'users')   # 标识符
  ('LBRACK', '[')        # 左方括号
  ('ID',     'age')      # 标识符
  ('OP',     '>')        # 比较操作符
  ('NUM',     25)        # 整数字面量（已转为 int）
  ('RBRACK', ']')        # 右方括号
  ('DOT',    '.')        # 点号
  ('ID',     'name')     # 标识符
```

**示例：** 对带管道的查询 `users[age>25] | sort(age) | take(2) | .name` 进行词法分析后产出：
```
Tokens:
  ('ID',     'users')   ('LBRACK', '[')   ('ID', 'age')   ('OP', '>')   ('NUM', 25)   ('RBRACK', ']')
  ('PIPE',   '|')       ('ID', 'sort')    ('LPAREN', '(') ('ID', 'age') ('RPAREN', ')')
  ('PIPE',   '|')       ('ID', 'take')    ('LPAREN', '(') ('NUM', 2)    ('RPAREN', ')')
  ('PIPE',   '|')       ('DOT', '.')      ('ID', 'name')
```

#### 2. 语法分析 `class Parser` 与 AST 节点设计
**目标：** 将线性的 Token 列表组合成一棵具有层次结构的**抽象语法树 (AST, Abstract Syntax Tree)**。
- **AST 节点定义：** 在 `json_dsl.py` 开头预定义了所有的行为节点（继承自 `ASTNode`）：
  - `Query`: 整体查询，包含多个管道阶段 (stages)。
  - `Path`: 连续的属性获取路径，如 `a.b.c`。
  - `GetField` / `IndexAccess`: 具体的对象属性读取和数组索引读取。
  - `Filter`: 带有条件的数组过滤操作 `[...]`。
  - `BinOp` / `FuncCall`: 二元操作符运算和函数调用。
- **解析机制 (Recursive Descent)：** 
  `Parser` 类持有传入的 token 列表，通过不断的预测 (`peek`) 和消费 (`consume`) 来构建树结构。
  例如 `parse()` 方法会识别最外层的管道符 `|`：
  ```python
  def parse(self):
      stages = [self.parse_stage()]
      while self.peek() and self.peek()[0] == 'PIPE':
          self.consume('PIPE')
          stages.append(self.parse_stage())
      return Query(stages)
  ```
- **产出结果：** 生成一棵多层的嵌套对象，作为查询动作的结构化表达。

**示例：** 对查询 `users[age>25].name` 解析后生成的 AST：
```
Query
 └─ stages[0]: Path
     ├─ steps[0]: GetField(name="users", safe=False)
     ├─ steps[1]: Filter
     │   └─ condition: BinOp
     │       ├─ left:  Ident(name="age")
     │       ├─ op:    ">"
     │       └─ right: Literal(value=25)
     └─ steps[2]: GetField(name="name", safe=False)
```

**示例：** 对带管道的查询 `users[age>25] | sort(age) | .name` 解析后生成的 AST：
```
Query
 ├─ stages[0]: Path
 │   ├─ steps[0]: GetField(name="users", safe=False)
 │   └─ steps[1]: Filter
 │       └─ condition: BinOp(left=Ident("age"), op=">", right=Literal(25))
 ├─ stages[1]: FuncCall(name="sort", args=[Ident("age")])
 └─ stages[2]: Path
     └─ steps[0]: GetField(name="name", safe=False)
```

#### 3. 求值器 `class DSLEvaluator`
**目标：** 拿着已生成的 AST，一步步地施加在输入的 JSON 数据上。
- **具体实现：** 
  设计了递归执行函数 `evaluate(node, data)` 以及用于解析条件的 `evaluate_cond(node, data)`。不同类型的 AST 节点有不同的处理逻辑：
  - **`Query` 节点**：将前一个管道阶段（`stage`）产生的数据，传递给下一个阶段执行（实现 `|` 管道运算）。
  - **`GetField` 节点**：
    如果当前操作的数据对象是 `dict`，则调用 `data.get()`；
    如果当前操作的数据对象是 `list`，则循环遍历该数组，获取每个对象的指定属性（**自动数组映射**）。
  - **`Filter` 节点**：先递归调用 `evaluate_cond` 对数组中的每一个元素的具体条件进行布尔判断，保留返回 `True` 的项。
  - **自定义函数节点 `FuncCall`**：当解析器识别到带有 `(arg)` 的节点，比如 `sort`、`take` ，就在 `self.custom_functions` 找到用户自定义传入的回调函数，并传递 `data` 作为参数执行对应函数。
  - **`BinOp` 节点**：针对在 `Filter` 里的操作，分别计算左右两边的值，执行具体的 Python `==, !=, >, <, in, str.startswith` 运算。
  - **`FuncCall` 节点**：读取类中 `self.custom_functions` 注册表，寻找开发者已注册的方法（如 `sort`, `take`），并执行计算。
- **产出结果：** 整个递归调用栈完结后，返回经过筛选或处理的目标 JSON 数据片段。

---

## 四、测试策略与考量

目前的测试体系包含 5 个模块，共计 **82 条用例**。

### 4.1 单元测试（Unit Test）
解耦三大核心模块，独立验证：
- **Lexer**：验证 Token 拆分、类型转换、以及源码位置（Position Tracking）的精确度。
- **Parser**：验证各语法成分生成的 AST 树结构是否正确，优先级计算是否符合预期。
- **Evaluator**：手动构造 AST 节点注入，验证执行引擎的运算逻辑。

### 4.2 集成测试（Integration Test）
端到端验证 CLI 体验：
- 验证命令行参数解析、文件读取、stdin 数据流处理。
- 验证不同形态的错误（文件不存在、语法错、未注册函数）能否给出正确的退出码 (Exit Code) 和 stderr 提示。

### 4.3 模糊测试（Fuzz Testing）
面向不可控输入的鲁棒性验证：
- 随机生成几百条语法合法或绝对非法的垃圾字符串进行“狂轰滥炸”。
- 目标：系统绝不能抛出 `IndexError` / `TypeError` 等内部异常崩溃，所有的错误必须被优雅拦截并转化为 `DSLSyntaxError` 或 `DSLRuntimeError`。

### 4.4 属性测试（Property-Based Testing）
验证数据流转的不变性质 (Invariants)：
- **长度保持**：`users.name` 产出数组的长度必等于原数组。
- **子集属性**：`users[age > X]` 里的每一个元素，必然在原数组中，且必然满足其验证条件。
- **单调性**：随着 `X` 变大，`users[age > X]` 的结果数量单调不增。

### 4.5 回归功能测试（Regression E2E Test）
- **功能正确性**：路径取值、数组映射、条件过滤、多层管道链流转。
- **操作符与边界**：越界索引（安全与非安全）、负索引、空数组过滤、多层括号嵌套等 edge cases。

### 4.6 测试运行

```bash
make test
# 或
python3 -m unittest discover -s test -v
```

```
Ran 82 tests in 0.763s
OK
```

---

## 五、性能基准测试

通过 `benchmark.py` 生成 1000 条随机用户数据，对 11 种查询场景各执行 50 次取平均耗时：

| 查询场景 | 查询表达式 | 1000条 平均耗时 |
|---------|-----------|:-------------:|
| 简单路径取值 | `users[0].name` | ~0.04 ms |
| 数组映射 | `users.name` | ~0.2 ms |
| 条件过滤 | `users[age > 30].name` | ~1.3 ms |
| 复合条件 (and) | `users[age > 25 and active == true].name` | ~2.8 ms |
| 管道: filter + sort + take | `users[active==true] \| sort(score) \| take(10) \| .name` | ~1.1 ms |

可扩展性测试（查询 `users[age > 30].name`）：

| 数据量 | 平均耗时 | 吞吐量 |
|-------:|--------:|-------:|
| 100 | 0.15 ms | ~6500 qps |
| 1,000 | 1.3 ms | ~800 qps |
| 5,000 | 5.9 ms | ~170 qps |
| 10,000 | 12.4 ms | ~80 qps |

耗时与数据量基本呈线性关系 O(n)，符合预期——每条查询只需遍历一次数组。
