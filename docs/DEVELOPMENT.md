# Development Guide

本文档面向 BiliObjCLint 的开发者和贡献者。

## 项目结构

```
BiliObjCLint/
├── Formula/
│   └── biliobjclint.rb       # Homebrew formula
├── oclint/                   # OCLint 源码（BSD 3-Clause）
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
│   │   ├── oclint_runner.py  # OCLint 封装
│   │   ├── reporter.py       # 输出格式化
│   │   ├── rule_engine.py    # Python 规则引擎
│   │   └── logger.py         # 日志系统
│   ├── rules/                # 内置 Python 规则
│   │   ├── naming_rules.py   # 命名规则
│   │   ├── memory_rules.py   # 内存管理规则
│   │   ├── style_rules.py    # 代码风格规则
│   │   └── security_rules.py # 安全规则
│   ├── others/               # 辅助脚本
│   │   ├── release.sh        # 版本发布脚本
│   │   └── commit.sh         # 提交脚本
│   └── lib/
│       └── logging.sh        # Shell 日志库
├── custom_rules/
│   ├── python/               # 自定义 Python 规则
│   └── cpp/                  # 自定义 C++ 规则
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
- 调用规则引擎和 OCLint
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
    --files test/TestFile.m \
    --verbose

# 仅运行 Python 规则
.venv/bin/python3 scripts/biliobjclint.py \
    --files test/TestFile.m \
    --no-oclint

# JSON 输出
.venv/bin/python3 scripts/biliobjclint.py \
    --files test/TestFile.m \
    --json-output
```

## 添加新的内置规则

1. 在 `scripts/rules/` 下创建或修改规则文件
2. 在 `scripts/rules/__init__.py` 中注册规则
3. 在 `config/default.yaml` 中添加默认配置
4. 更新 README 的规则列表

## 代码规范

- Python: 遵循 PEP 8
- 使用类型注解
- 添加文档字符串
- 错误处理要完善

## 提交规范

```bash
# 提交格式
<type>: <description>

# 类型
feat:     新功能
fix:      Bug 修复
docs:     文档更新
refactor: 代码重构
test:     测试相关
chore:    构建/工具更新
```
