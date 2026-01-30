<p align="center">
  <h1 align="center">BiliObjCLint</h1>
  <p align="center">集成 Xcode 和 Claude AI 自动修复的 Objective-C 代码检查工具</p>
  <p align="center">
    <a href="README.md">English</a> | <a href="README.zh-CN.md">简体中文</a>
  </p>
</p>

---

## 功能特性

- **增量检查**: 仅检查 Git 变更的代码，快速高效
- **Xcode 集成**: 输出原生 Xcode 警告/错误格式
- **双引擎架构**:
  - OCLint: 70+ 内置规则，深度 AST 分析
  - Python 规则引擎: 轻量、快速、易扩展
- **Claude AI 自动修复**: 使用 Claude Code CLI 自动修复代码问题
- **高度可配置**: YAML 配置文件，灵活的规则定制
- **易于扩展**: 支持 Python 和 C++ 自定义规则

## 环境要求

- macOS 10.15+
- Python 3.9+
- Xcode 12+（用于 Xcode 集成）
- Git（用于增量检查）

## 安装

### 通过 Homebrew（推荐）

```bash
# 添加 tap 并安装
brew tap pjocer/biliobjclint
brew install biliobjclint

# 更新到最新版本
brew update && brew upgrade biliobjclint
```

### 手动安装

```bash
# 克隆仓库
git clone https://github.com/pjocer/BiliObjcLint.git
cd BiliObjcLint

# 初始化 Python 虚拟环境
./scripts/bin/setup_env.sh
```

## 快速开始

### 1. 基本用法

```bash
# 检查所有文件
biliobjclint

# 增量检查（仅 Git 变更）
biliobjclint --incremental

# 检查指定文件
biliobjclint --files path/to/File.m

# 详细输出
biliobjclint --verbose
```

### 2. Xcode 集成

```bash
# 对于 .xcodeproj
biliobjclint-xcode /path/to/App.xcodeproj

# 对于 .xcworkspace（需指定项目名称）
biliobjclint-xcode /path/to/App.xcworkspace -p MyProject

# 指定 Target
biliobjclint-xcode /path/to/App.xcworkspace -p MyProject -t MyTarget

# 列出 workspace 中的所有项目
biliobjclint-xcode /path/to/App.xcworkspace --list-projects

# 列出所有 Target
biliobjclint-xcode /path/to/App.xcodeproj --list-targets
```

这将会：
1. 在 Xcode 项目中添加 Build Phase 脚本
2. 复制默认配置文件到项目根目录

### 3. 自动 Bootstrap 模式（推荐用于多项目 Workspace）

自动复制 bootstrap.sh 并注入 Package Manager Build Phase，自动计算正确的相对路径：

```bash
# 对于 workspace（推荐用于复杂项目结构）
biliobjclint-xcode /path/to/App.xcworkspace -p MyProject -t MyTarget --bootstrap

# 对于 xcodeproj
biliobjclint-xcode /path/to/App.xcodeproj -t MyTarget --bootstrap

# 预览修改，不实际应用
biliobjclint-xcode /path/to/App.xcworkspace -p MyProject -t MyTarget --bootstrap --dry-run
```

这将会：
1. 复制 `bootstrap.sh` 到 `./scripts/` 目录（与 workspace/xcodeproj 同级）
2. 自动计算从 SRCROOT 到 scripts 目录的相对路径
3. 添加 `[BiliObjcLint] Package Manager` Build Phase，使用自动计算的路径

这对于 SRCROOT 与 workspace 根目录不同的工作空间特别有用。

### 4. Bootstrap 脚本（手动配置）

使用 bootstrap 脚本自动安装和配置 BiliObjCLint：

**第一步：复制 bootstrap.sh 到你的项目**
```bash
mkdir -p /path/to/your/project/scripts
cp $(brew --prefix)/share/biliobjclint/scripts/bin/bootstrap.sh /path/to/your/project/scripts/
```

**第二步：在 Xcode 中添加 Build Phase**
1. 用 Xcode 打开你的 `.xcworkspace` 或 `.xcodeproj`
2. 在导航器中选择你的项目
3. 选择要添加 Lint 的 Target
4. 切换到 **Build Phases** 标签页
5. 点击 **+** → **New Run Script Phase**
6. 将新建的 Phase 拖动到**最顶部**（所有其他 Phase 之前）
7. 粘贴以下脚本：
```bash
"${SRCROOT}/scripts/bootstrap.sh" -w "${WORKSPACE_PATH}" -p "${PROJECT_FILE_PATH}" -t "${TARGET_NAME}"
```
> 注意: `${WORKSPACE_PATH}` 是 workspace 完整路径，`${PROJECT_FILE_PATH}` 是 .xcodeproj 完整路径

**bootstrap 脚本会自动：**
1. 检查 BiliObjCLint 是否已安装，未安装则通过 Homebrew 安装
2. 后台静默检测新版本（每 24 小时一次，通过 GitHub Tags API，不阻塞编译）
3. 发现新版本时自动执行 `brew upgrade`，完成后通过系统通知提示版本和更新内容
4. 检查 Lint Build Phase 是否存在，不存在则自动注入
5. 检查 Lint Build Phase 版本，有更新时自动升级脚本

### 5. 安装 OCLint（可选）

如果需要 OCLint 的深度 AST 分析：

```bash
brew install oclint
```

## 配置

在项目根目录创建 `.biliobjclint.yaml`：

```yaml
# 基本设置
base_branch: "origin/master"
incremental: true
fail_on_error: true

# 文件过滤
excluded:
  - "Pods/**"
  - "Vendor/**"
  - "ThirdParty/**"

# Python 规则
python_rules:
  class_prefix:
    enabled: true
    severity: warning
    params:
      prefix: "BL"

  weak_delegate:
    enabled: true
    severity: error

  line_length:
    enabled: true
    params:
      max_length: 120

# OCLint 设置
oclint:
  enabled: true
  rule_configurations:
    - key: LONG_METHOD
      value: 80
    - key: CYCLOMATIC_COMPLEXITY
      value: 10

# Claude 自动修复设置
claude_autofix:
  trigger: "any"     # any | error | disable
  mode: "silent"     # silent | terminal | vscode
  timeout: 120
```

完整示例请参考 `config/default.yaml`。

## 内置规则

### Python 规则

| 规则 ID | 描述 | 默认级别 |
|---------|------|----------|
| `class_prefix` | 类名前缀检查 | warning |
| `property_naming` | 属性命名（小驼峰） | warning |
| `constant_naming` | 常量命名检查 | warning |
| `method_naming` | 方法命名检查 | warning |
| `line_length` | 行长度限制 | warning |
| `method_length` | 方法长度限制 | warning |
| `todo_fixme` | TODO/FIXME 检测 | warning |
| `weak_delegate` | Delegate 应使用 weak | error |
| `block_retain_cycle` | Block 循环引用检测（含 weak/strong self 检查） | warning |
| `wrapper_empty_pointer` | 容器字面量空指针检查 | warning |
| `dict_usage` | 字典 setObject:forKey: 使用检查 | warning |
| `collection_mutation` | 集合修改操作安全检查 | warning |
| `forbidden_api` | 禁用 API 检查 | error |
| `hardcoded_credentials` | 硬编码凭据检测 | error |
| `insecure_random` | 不安全随机数生成检测 | warning |
| `file_header` | 文件头注释检查 | warning |

### OCLint 规则

OCLint 提供 70+ 规则，涵盖：Basic、Convention、Empty、Naming、Redundant、Size、Unused 等类别。

## 命令行选项

### biliobjclint

```
biliobjclint [options]

选项:
  --config, -c PATH       配置文件路径
  --project-root, -p PATH 项目根目录
  --incremental, -i       增量检查模式
  --base-branch, -b NAME  增量比较的基准分支
  --files, -f FILE...     指定检查的文件
  --xcode-output, -x      Xcode 格式输出（默认）
  --json-output, -j       JSON 格式输出
  --no-oclint             禁用 OCLint
  --no-python-rules       禁用 Python 规则
  --verbose, -v           详细输出
```

### biliobjclint-xcode

```
biliobjclint-xcode <项目路径> [选项]

选项:
  --project, -p NAME      项目名称（用于 workspace）
  --target, -t NAME       Target 名称（默认：主 Target）
  --remove                移除 Lint Phase
  --bootstrap             复制 bootstrap.sh 并注入 Package Manager Build Phase
  --check-update          检查已注入脚本是否需要更新
  --list-projects         列出 workspace 中所有项目
  --list-targets          列出所有可用的 Targets
  --dry-run               仅显示将要进行的修改
  --override              强制覆盖已存在的 Lint Phase
```

## 常见问题

### Q: 如何只检查特定类型的问题？

在 `.biliobjclint.yaml` 中禁用不需要的规则：

```yaml
python_rules:
  todo_fixme:
    enabled: false
```

### Q: 如何忽略特定文件？

在配置中添加排除模式：

```yaml
excluded:
  - "**/*Generated*.m"
  - "Legacy/**"
```

### Q: OCLint 编译失败？

仅使用 Python 规则：

```bash
biliobjclint --no-oclint
```

### Q: 如何使用 Claude 自动修复？

1. 安装 [Claude Code CLI](https://claude.ai/code)
2. 在 `~/.zshrc` 或 `~/.bashrc` 中配置 Claude 环境变量：

```bash
# 必须：API 端点和认证信息
export ANTHROPIC_BASE_URL=https://api.anthropic.com  # 或你的自定义端点
export ANTHROPIC_AUTH_TOKEN=your-api-key-here

# 可选：模型和超时设置
export ANTHROPIC_MODEL=claude-4.5-opus
export API_TIMEOUT_MS=600000
```

> **重要**：这些环境变量必须配置在 shell 配置文件（`.zshrc` 或 `.bashrc`）中，因为 Xcode Build Phase 作为后台进程运行，不会继承终端会话的环境变量。

3. 在 `.biliobjclint.yaml` 中配置：

```yaml
claude_autofix:
  trigger: "any"
  mode: "silent"
```

## 文档

| 文档 | 说明 |
|------|------|
| [自定义规则](docs/CUSTOM_RULES.md) | 如何创建自定义 lint 规则 |
| [开发指南](docs/DEVELOPMENT.md) | 项目结构和开发说明 |
| [版本发布](docs/RELEASE.md) | 版本发布流程 |

## 贡献

欢迎贡献！请随时提交 Issue 和 Pull Request。

## 许可证

本项目基于 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

本项目包含 OCLint，其基于 BSD 3-Clause 许可证。
