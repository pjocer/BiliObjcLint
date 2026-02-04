# Development Guide

本文档面向 BiliObjCLint 的开发者和贡献者。

## 项目结构

```
BiliObjCLint/
├── Formula/
│   └── biliobjclint.rb           # Homebrew formula
├── scripts/
│   ├── __init__.py               # 顶层包导出
│   ├── bin/                      # 可执行脚本
│   │   ├── biliobjclint.sh       # biliobjclint 命令入口
│   │   ├── biliobjclint-xcode.sh # Xcode 集成命令入口
│   │   └── biliobjclint-server.sh# Server 命令入口
│   ├── claude/                   # Claude AI 自动修复模块
│   │   ├── fixer.py              # 修复器主逻辑
│   │   ├── http_server.py        # HTTP 服务器（处理浏览器请求）
│   │   └── html_report.py        # HTML 报告生成
│   ├── core/                     # 核心模块
│   │   ├── lint/                 # Lint 核心模块
│   │   │   ├── config.py         # 配置管理
│   │   │   ├── git_diff.py       # Git 增量检测
│   │   │   ├── reporter.py       # 输出格式化
│   │   │   ├── rule_engine.py    # Python 规则引擎
│   │   │   ├── logger.py         # 日志系统
│   │   │   └── rules/            # 内置 Python 规则
│   │   │       ├── naming_rules/ # 命名规则
│   │   │       ├── memory_rules/ # 内存管理规则
│   │   │       ├── style_rules/  # 代码风格规则
│   │   │       └── security_rules/# 安全规则
│   │   └── server/               # 本地统计服务模块
│   ├── wrapper/                  # 应用层封装
│   │   ├── lint/                 # Lint 入口
│   │   │   ├── linter.py         # BiliObjCLint 主类
│   │   │   └── cli.py            # 命令行入口
│   │   ├── update/               # 更新模块
│   │   │   ├── checker.py        # 版本检查
│   │   │   ├── upgrader.py       # 后台升级
│   │   │   └── phase_updater.py  # Build Phase 更新（子进程）
│   │   └── xcode/                # Xcode 集成
│   │       ├── integrator.py     # XcodeIntegrator 主类
│   │       ├── project_loader.py # 项目加载
│   │       ├── phase_manager.py  # Build Phase 管理
│   │       ├── bootstrap.py      # Bootstrap 逻辑
│   │       ├── templates.py      # 脚本模板
│   │       └── cli.py            # 命令行入口
│   ├── others/                   # 辅助脚本
│   │   ├── release.sh            # 版本发布脚本
│   │   └── commit.sh             # 提交脚本
│   └── lib/
│       └── logging.sh            # Shell 日志库
├── config/
│   ├── default.yaml              # 默认配置模板
│   ├── bootstrap.sh              # Bootstrap 脚本（自动安装/更新）
│   └── code_style_check.sh       # 代码规范审查脚本
├── custom_rules/
│   └── python/                   # 自定义 Python 规则
├── docs/                         # 开发文档
├── logs/                         # 运行日志（gitignore）
├── setup_env.sh                  # 环境初始化脚本
└── VERSION                       # 版本号文件
```

## 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/pjocer/BiliObjcLint.git
cd BiliObjcLint

# 初始化 Python 虚拟环境
./setup_env.sh

# 激活虚拟环境（可选，用于开发调试）
source .venv/bin/activate
```

## 核心模块说明

### wrapper/lint/linter.py

BiliObjCLint 主类，负责：
- 加载配置
- 获取待检查文件
- 调用规则引擎
- 输出结果

命令行入口：`wrapper/lint/cli.py`

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

### biliobjclint-server

本地统计服务，用于接收 lint 上报并提供可视化仪表盘。

配置模板：
[config/biliobjclint_server_config.json](../config/biliobjclint_server_config.json)

接口规范：
[LINTSERVER.md](../LINTSERVER.md)

配置文件可由 biliobjclint-server 自动创建，或自行基于模板创建并编辑。

使用方式：

```bash
# 直接运行脚本
scripts/bin/biliobjclint-server.sh --start
scripts/bin/biliobjclint-server.sh --stop
scripts/bin/biliobjclint-server.sh --restart
scripts/bin/biliobjclint-server.sh --status

# 安装后入口
# 由 Homebrew formula 创建 wrapper 提供
biliobjclint-server start
biliobjclint-server restart

# Homebrew Services
brew services start biliobjclint-server
brew services stop biliobjclint-server
brew services restart biliobjclint-server
```

### reporter.py

输出格式化，支持：
- Xcode 格式（默认）
- JSON 格式
- 违规去重和排序

## 日志系统

### 日志文件位置

**开发模式**（本地运行）：
- 日志位于项目根目录的 `logs/` 目录

**Homebrew 安装后**：
- 日志位于 brew 安装目录：`$(brew --prefix biliobjclint)/libexec/logs/`

```bash
# 获取 Homebrew 安装后的日志目录
brew_logs="$(brew --prefix biliobjclint)/libexec/logs"

# 查看最新日志
ls -lt "$brew_logs" | head -10

# 实时查看 background_upgrade 日志
tail -f "$brew_logs"/background_upgrade_*.log

# 实时查看 check_update 日志
tail -f "$brew_logs"/check_update_*.log
```

**后台升级调试日志**：
- 位于用户目录：`~/.biliobjclint/background_upgrade.log`
- 包含 shell 命令和参数信息

```bash
# 查看后台升级调试日志
cat ~/.biliobjclint/background_upgrade.log
```

**scripts 路径持久化存储**：
- 位于用户目录：`~/.biliobjclint/scripts_paths.json`
- 存储 `--bootstrap` 执行时计算的 scripts 相对路径
- Key 格式：`{project_path}|{project_name}|{target_name}`
- Value：scripts 目录相对于 SRCROOT 的路径

```bash
# 查看 scripts 路径配置
cat ~/.biliobjclint/scripts_paths.json
```

### 日志文件类型

| 文件模式 | 说明 |
|---------|------|
| `biliobjclint_*.log` | 主 lint 日志 |
| `check_update_*.log` | 版本检查日志 |
| `background_upgrade_*.log` | 后台升级日志 |
| `xcode_*.log` | Xcode 集成日志 |
| `claude_fix_*.log` | Claude 修复日志 |

### 日志级别

- `DEBUG`: 详细调试信息
- `INFO`: 一般运行信息
- `WARNING`: 警告信息
- `ERROR`: 错误信息

### 启用详细日志输出

设置环境变量可在控制台输出 INFO 级别日志：

```bash
export BILIOBJCLINT_VERBOSE=1
```

## 测试

```bash
# 检查测试文件
.venv/bin/python3 scripts/wrapper/lint/cli.py \
    --files tests/TestFile.m \
    --verbose

# JSON 输出
.venv/bin/python3 scripts/wrapper/lint/cli.py \
    --files tests/TestFile.m \
    --json-output
```

## 本地调试

开发 BiliObjCLint 时，可以使用调试模式在目标 Xcode 项目中直接测试本地代码，无需发布新版本到 Homebrew。

### 启用调试模式

```bash
# 1. 初始化本地开发环境
./setup_env.sh

# 2. 对目标 Xcode 项目启用调试模式
biliobjclint-xcode /path/to/App.xcodeproj --bootstrap \
    --debug /path/to/BiliObjCLint
```

### 调试模式 vs 正常模式

| 特性 | 正常模式 | 调试模式 |
|------|----------|----------|
| 代码来源 | Homebrew 安装目录 | 本地开发目录 |
| Python 环境 | `$(brew --prefix)/libexec/.venv` | 本地 `.venv` |
| 版本检查 | 自动检查 GitHub 更新 | 跳过（避免覆盖本地代码） |
| 脚本复制 | 从 brew prefix 复制 | 从本地目录复制 |
| 配置文件 | 目标项目的 `.biliobjclint.yaml` | 同左 |
| 标记文件 | 无 | `scripts/.biliobjclint_debug` |

### 退出调试模式

```bash
# 方式 1: 删除标记文件
rm /path/to/App/scripts/.biliobjclint_debug

# 方式 2: 重新执行 bootstrap（不带 --debug）
biliobjclint-xcode /path/to/App.xcodeproj --bootstrap
```

### 开发工作流

```bash
# 1. 在 BiliObjCLint 项目中修改代码

# 2. 在目标 Xcode 项目中编译，直接测试修改效果
#    Xcode: Product -> Build

# 3. 测试通过后提交代码，发布新版本
./scripts/others/commit.sh -y -t feat -d "新功能"
./scripts/others/release.sh -y

# 4. 退出调试模式，验证 Homebrew 安装版本
rm /path/to/App/scripts/.biliobjclint_debug
```

### 注意事项

1. **venv 必须先初始化**: 调试模式使用本地 `.venv`，必须先执行 `./setup_env.sh`
2. **跳过版本检查**: 调试模式会跳过版本更新检查，避免后台升级覆盖本地代码
3. **gitignore**: `.biliobjclint_debug` 文件应加入目标项目的 `.gitignore`
4. **日志位置**: 调试模式下日志写入本地 `logs/` 目录

## 添加新的内置规则

1. 在 `scripts/core/lint/rules/` 下创建或修改规则文件
2. 在 `scripts/core/lint/rules/__init__.py` 中注册规则
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
| `-i, --important` | 重要提示（可选，可多次使用，自动写入 CHANGELOG 的 `### 重要` 段落） |
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

# 带重要提示（自动写入 CHANGELOG，更新时高亮显示）
./scripts/others/commit.sh -y -t feat -d "重大架构更新" \
    -i "需要重新执行 --bootstrap" \
    -i "旧版本配置不兼容"

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

详见 [RELEASE.md](RELEASE.md)。

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
