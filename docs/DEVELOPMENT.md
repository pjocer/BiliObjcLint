# Development Guide

本文档面向 BiliObjCLint 的开发者和贡献者。

## 项目结构

```
BiliObjCLint/
├── Formula/
│   └── biliobjclint.rb       # Homebrew formula
├── scripts/
│   ├── biliobjclint.py       # 主入口
│   ├── xcode_integrator.py   # Xcode 集成工具
│   ├── bin/                  # 可执行脚本
│   │   ├── biliobjclint.sh   # biliobjclint 命令入口
│   │   ├── biliobjclint-xcode.sh  # Xcode 集成命令入口
│   │   ├── bootstrap.sh      # Bootstrap 脚本（自动安装/更新）
│   │   └── setup_env.sh      # 环境初始化脚本
│   ├── claude/               # Claude AI 自动修复模块
│   │   ├── fixer.py          # 修复器主逻辑
│   │   ├── http_server.py    # HTTP 服务器（处理浏览器请求）
│   │   └── html_report.py    # HTML 报告生成
│   ├── core/                 # 核心模块
│   │   ├── config.py         # 配置管理
│   │   ├── git_diff.py       # Git 增量检测
│   │   ├── reporter.py       # 输出格式化
│   │   ├── rule_engine.py    # Python 规则引擎
│   │   └── logger.py         # 日志系统
│   ├── rules/                # 内置 Python 规则
│   │   ├── naming_rules/     # 命名规则
│   │   ├── memory_rules/     # 内存管理规则
│   │   ├── style_rules/      # 代码风格规则
│   │   └── security_rules/   # 安全规则
│   ├── others/               # 辅助脚本
│   │   ├── release.sh        # 版本发布脚本
│   │   └── commit.sh         # 提交脚本
│   └── lib/
│       └── logging.sh        # Shell 日志库
├── custom_rules/
│   └── python/               # 自定义 Python 规则
├── config/
│   └── default.yaml          # 默认配置模板
├── docs/                     # 开发文档
├── logs/                     # 运行日志（gitignore）
└── VERSION                   # 版本号文件
```

## 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/pjocer/BiliObjcLint.git
cd BiliObjcLint

# 初始化 Python 虚拟环境
./scripts/bin/setup_env.sh

# 激活虚拟环境（可选，用于开发调试）
source .venv/bin/activate
```

## 核心模块说明

### biliobjclint.py

主入口，负责：
- 解析命令行参数
- 加载配置
- 获取待检查文件
- 调用规则引擎
- 输出结果

### rule_engine.py

Python 规则引擎，负责：
- 加载内置规则
- 加载自定义规则
- 执行规则检查
- 收集违规结果

### claude/ 模块

Claude AI 自动修复模块，包含以下文件：

**fixer.py** - 修复器主逻辑：
- 检测 Claude Code CLI 可用性
- 根据配置决定是否触发修复
- 构建修复 prompt
- 调用 Claude 执行修复
- 支持 silent（静默）和 terminal 模式

**http_server.py** - HTTP 服务器：
- 处理浏览器的修复请求（fix/cancel/ignore）
- 支持单个修复和批量"修复全部"
- 异步任务处理和状态轮询

**html_report.py** - HTML 报告生成：
- 生成交互式违规报告页面
- 支持代码预览和高亮
- 支持在 Xcode 中打开文件
- "修复全部"按钮（v1.1.8+）

### reporter.py

输出格式化，支持：
- Xcode 格式（默认）
- JSON 格式
- 违规去重和排序

## 日志系统

日志文件位于 `logs/` 目录：

```bash
# 查看最新日志
ls -lt logs/ | head -5

# 实时查看日志
tail -f logs/biliobjclint_*.log
```

日志级别：
- `DEBUG`: 详细调试信息
- `INFO`: 一般运行信息
- `WARNING`: 警告信息
- `ERROR`: 错误信息

## 测试

```bash
# 检查测试文件
.venv/bin/python3 scripts/biliobjclint.py \
    --files tests/TestFile.m \
    --verbose

# JSON 输出
.venv/bin/python3 scripts/biliobjclint.py \
    --files tests/TestFile.m \
    --json-output
```

## 添加新的内置规则

1. 在 `scripts/rules/` 下创建或修改规则文件
2. 在 `scripts/rules/__init__.py` 中注册规则
3. 在 `config/default.yaml` 中添加默认配置
4. 更新 README 的规则列表

## 规则开发 API

### create_violation 方法

所有规则都继承自 `BaseRule`，可以使用 `create_violation` 方法创建违规记录：

```python
def create_violation(
    self,
    file_path: str,                              # 文件路径
    line: int,                                   # 违规行号（从 1 开始）
    column: int,                                 # 违规列号（从 1 开始）
    message: str,                                # 违规消息
    related_lines: Optional[Tuple[int, int]] = None  # 关联行范围（可选）
) -> Violation
```

### related_lines 参数

`related_lines` 是一个可选的元组 `(start_line, end_line)`，用于指定违规相关的行范围。

**用途**：在增量检查模式下，`filter_by_changed_lines` 会检查以下条件之一是否满足：
1. `violation.line` 在 `changed_lines` 中
2. `violation.related_lines` 范围内有任意一行在 `changed_lines` 中

**适用场景**：
- **method_length** - 方法过长时，警告报告在方法定义行，但需要检查整个方法范围内是否有改动
- **class_length** - 类过长检查
- **block_retain_cycle** - block 跨多行时的循环引用检查
- 任何需要检查「代码块整体」的规则

### 使用示例

**基本用法**（不使用 related_lines）：

```python
def check(self, file_path, content, lines, changed_lines):
    violations = []
    for line_num, line in enumerate(lines, 1):
        if self.detect_issue(line):
            violations.append(self.create_violation(
                file_path=file_path,
                line=line_num,
                column=1,
                message="发现问题"
            ))
    return violations
```

**使用 related_lines**（检查代码块整体）：

```python
def check(self, file_path, content, lines, changed_lines):
    violations = []

    # 假设检测到一个方法从第 10 行到第 100 行
    method_start = 10
    method_end = 100
    method_length = method_end - method_start + 1

    if method_length > 80:
        # 警告报告在方法定义行（第 10 行）
        # 但增量过滤时会检查整个方法范围（10-100 行）是否有改动
        violations.append(self.create_violation(
            file_path=file_path,
            line=method_start,  # 报告位置：方法定义行
            column=1,
            message=f"方法过长，共 {method_length} 行",
            related_lines=(method_start, method_end)  # 关联范围：整个方法
        ))

    return violations
```

### 增量过滤流程

1. 规则检查生成 `Violation` 列表
2. `reporter.filter_by_changed_lines()` 过滤违规：
   - 如果 `violation.line` 在 `changed_lines` 中 → 保留
   - 如果 `violation.related_lines` 与 `changed_lines` 有交集 → 保留
   - 否则 → 过滤掉

```
示例：
- 方法定义在第 10 行
- 方法结束在第 100 行
- 用户修改了第 50 行
- related_lines = (10, 100)

过滤检查：
- violation.line (10) 不在 changed_lines → 继续检查
- related_lines (10-100) 包含 50，与 changed_lines 有交集 → 保留违规
```

## 代码规范

- Python: 遵循 PEP 8
- 使用类型注解
- 添加文档字符串
- 错误处理要完善

## 提交和发布

BiliObjCLint 提供了两个脚本来简化提交和发布流程：

### commit.sh - 提交脚本

同时提交改动到主仓库和 Homebrew tap 仓库，支持 Conventional Commits 格式。

```bash
# 脚本位置
./scripts/others/commit.sh

# 查看帮助
./scripts/others/commit.sh -h
```

**参数说明：**

| 参数 | 说明 |
|------|------|
| `-t, --type` | 提交类型: feat/fix/docs/style/refactor/perf/test/chore |
| `-s, --scope` | 作用域（可选）: 如 规则, 配置, 脚本, Claude |
| `-d, --desc` | 简短描述（必填） |
| `-b, --body` | 详细说明（可选） |
| `-m, --message` | 完整提交信息（跳过格式化） |
| `-y, --yes` | 非交互式模式（跳过确认） |

**使用示例：**

```bash
# 交互式输入（会依次提示选择类型、输入作用域、描述、详情）
./scripts/others/commit.sh

# CLI 参数指定
./scripts/others/commit.sh -t feat -s "规则" -d "新增 method_parameter 规则"

# 非交互式提交
./scripts/others/commit.sh -y -t fix -d "修复增量检查失效问题"

# 带详细说明
./scripts/others/commit.sh -t feat -s "Claude" -d "添加 API 配置支持" \
    -b "- 支持内部网关配置
- 支持官方 API 配置"

# 直接指定完整信息（兼容旧方式）
./scripts/others/commit.sh -m "feat: 新增功能"
```

**提交格式：**

```
<type>[(<scope>)]: <description>

[body]

Co-Authored-By: Claude (claude-4.5-opus) <noreply@anthropic.com>
```

### release.sh - 发布脚本

发布新版本，自动完成以下操作：
1. 更新 VERSION 文件
2. 提交并推送到远程
3. 创建 Git tag
4. 计算 SHA256 并更新 Formula
5. 同步 Formula 到 Homebrew tap 仓库

```bash
# 脚本位置
./scripts/others/release.sh

# 查看帮助
./scripts/others/release.sh -h
```

**参数说明：**

| 参数 | 说明 |
|------|------|
| `-y, --yes` | 非交互式模式（跳过确认） |
| `patch` | 递增修订版本（默认）: v1.0.0 → v1.0.1 |
| `minor` | 递增次版本: v1.0.0 → v1.1.0 |
| `major` | 递增主版本: v1.0.0 → v2.0.0 |
| `vX.Y.Z` | 指定精确版本号 |

**使用示例：**

```bash
# 交互式发布（递增 patch 版本）
./scripts/others/release.sh

# 非交互式发布
./scripts/others/release.sh -y

# 递增 minor 版本
./scripts/others/release.sh minor

# 非交互式递增 minor 版本
./scripts/others/release.sh -y minor

# 指定精确版本
./scripts/others/release.sh v2.0.0
```

**注意事项：**
- 发布前必须先提交所有改动（可使用 commit.sh）
- 如有未提交改动，脚本会报错并提示
- Homebrew tap 仓库需要与主仓库在同一目录下

### 典型开发流程

```bash
# 1. 开发完成后，提交改动
./scripts/others/commit.sh -t feat -s "规则" -d "新增 xxx 规则"

# 2. 发布新版本
./scripts/others/release.sh -y

# 或者非交互式一键完成
./scripts/others/commit.sh -y -t feat -d "新增功能" && ./scripts/others/release.sh -y
```

## 提交类型说明

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档更新 |
| `style` | 代码格式（不影响功能） |
| `refactor` | 重构（既不是新功能也不是修复） |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `chore` | 构建/工具/依赖等杂项 |
