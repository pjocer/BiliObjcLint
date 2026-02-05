# BiliObjCLint 更新日志

所有重要的版本更新都会记录在此文件中。

## v1.4.6 (2026-02-05)

### 重构
- **P0.6 violation_id 统一设计**
  - 新增 `ViolationType` 命名元组：统一 `sub_type`、`message`、`severity`
  - 所有规则迁移到 ViolationType API，`create_violation()` 使用 `violation_type` 参数
  - Violation 新增 `rule_name` 字段：存储规则中文显示名称（如"循环引用"、"禁用 API"）
  - 移除 `create_violation_with_severity()` 方法（ViolationType 已支持自定义 severity）
  - `violation_id` 计算公式：`hash(file_path + rule_id + sub_type + code_hash + line_offset + column)`
  - 确保同一代码位置的同类违规产生稳定唯一 ID

- **P1 Server DB 重构**
  - Per-project violations 表设计：每个项目组合（project_key + project_name）独立表
  - 表名格式：`violations_{8字符MD5哈希}`
  - Dashboard 级联选择：project_key → project_name 联动下拉框
  - 修复 upsert 逻辑正确区分 insert/update 计数

### 新增
- 新增 `test_server_db.py` 测试模块（11 个测试用例）
  - DB Schema 验证：基础表创建、Per-project 表创建、表结构完整性
  - Violations Upsert：Violation 对象/字典格式、去重验证、数据完整性

### 改进
- `test_base_rule.py` 重写适配 ViolationType API
- 所有 133 个测试通过

## v1.4.5 (2026-02-05)

### 重构
- **P0.5 Violation 固有属性重构**
  - Violation 不可变性：所有属性在 `create_violation()` 时一次性确定，创建后不可修改
  - 统一序列化：所有序列化/反序列化通过 `Violation.to_dict()` / `Violation.from_dict()`
  - BaseRule 重构：删除 `get_hash_context()`，新增 `get_context()` 和 `compute_code_hash()`
  - `create_violation()` 签名变更：新增必填参数 `lines`，自动计算 `context` 和 `code_hash`
  - IgnoreCache 接口重构：`add_ignore()` / `is_ignored()` / `remove_ignore()` 改为接收 Violation 对象
  - Metrics 上报重构：使用 `Violation.to_dict()` 作为基础
  - Server 模块扩展：violations 表新增 `source`、`pod_name`、`related_lines`、`context` 字段

## v1.4.4 (2026-02-05)

### 修复
- 修复 violation 去重时机问题，确保 JSON 输出、Xcode 输出、Metrics 上报数据一致性
  - 将 `deduplicate()` 调用移到 JSON 文件输出之前，避免 Claude 对话显示未去重的数据
- 修复文件列表可能重复的问题
  - 主工程和本地 Pod 文件重叠时，同一文件会被检查两次，导致重复 violation
  - 添加文件列表去重逻辑

## v1.4.3 (2026-02-04)

### 修复
- 修复 Dashboard 显示累计数据而非去重数据的问题
  - Dashboard 现在从 `violations` 表获取去重后的实际违规数，而不是累加所有历史运行记录
  - 新增 `get_current_violations_summary()` 和 `get_current_rule_stats()` 方法
  - 修复 code_hash 为 NULL 时 UNIQUE 约束失效的问题（SQLite 中 NULL != NULL）

## v1.4.2 (2026-02-04)

### 新增
- Metrics 上报去重优化
  - 新增 `violation_hash.py` 模块，计算违规代码内容哈希
  - `BaseRule` 新增 `get_hash_context()` 接口，支持规则级别的哈希策略
  - 特殊规则实现自定义哈希范围：Block 范围、容器范围、方法范围、文件头范围
  - `Violation` 新增 `code_hash` 字段
  - Metrics Payload 新增 `violations` 列表（含 code_hash）
  - Server 端新增 `violations` 表，支持 UNIQUE 约束去重
  - Server 端实现 upsert 逻辑，相同违规只更新 `last_seen`
  - 新增 API：`GET /api/v1/violations`、`GET /api/v1/violations/stats`、`POST /api/v1/violations/cleanup`

## v1.4.1 (2026-02-04)

### 重构
- 重构 scripts 目录结构，拆分模块到 wrapper/
  - 迁移 `rules/` 到 `core/lint/rules/`
  - 创建 `wrapper/update/`：checker.py, upgrader.py, phase_updater.py
  - 拆分 `xcode_integrator.py` 到 `wrapper/xcode/`：integrator.py, project_loader.py, phase_manager.py, bootstrap.py, templates.py, cli.py
  - 迁移 `biliobjclint.py` 到 `wrapper/lint/`
  - 更新 `bin/*.sh` 脚本路径
  - 更新 `code_style_check.sh` 脚本路径引用

### 修复
- 使用子进程彻底解决 brew upgrade 后 Build Phase 版本不更新的问题
  - 根本原因：background_upgrade.py 从旧版本启动，进程中已加载旧版本模块
  - 修复方案：使用子进程在新版本的 Python 环境中执行 Build Phase 更新，完全隔离旧版本模块
- 添加 `xcode_integrator.py` 兼容层，确保旧版本升级时 Build Phase 更新正常
- 修复 CLI 脚本相对导入问题（改用绝对导入）

## v1.4.0 (2026-02-04)

### 新增
- 新增本地统计服务 `biliobjclint-server`
  - HTTP 服务器提供可视化 Dashboard（趋势图、规则统计、Autofix 汇总）
  - SQLite 存储 lint 历史数据
  - 用户认证和会话管理（登录、注册、记住密码）
  - 支持 `brew services start/stop biliobjclint`
- 新增客户端统计上报模块 (`metrics.py`)
  - 自动上报 lint 结果和 autofix 统计
  - 支持重试和 spool 兜底机制
- 新增 `metrics` 配置段（`config/default.yaml`）
  - `enabled`: 是否启用上报
  - `endpoint`: 服务端地址
  - `project_key`/`project_name`: 项目标识
- 新增 `biliobjclint-server clear` 命令，交互式清空本地缓存数据
- 新增 `AutofixTracker` 类，跟踪 Claude 自动修复统计
- 新增服务端配置模板 `config/biliobjclint_server_config.json`

### Dashboard 功能
- 趋势图支持动态粒度显示（同一天按小时、跨天按日期）
- 趋势图自动填充缺失时间段，数据点圆形标记
- 规则名显示中文（如 `todo_fixme` → `待办事项`），鼠标悬停显示英文 ID
- 启用状态改为 iOS 风格 toggle switch
- 登录页 B 站粉主题色（#fb7299）、logo 图片
- 用户注册功能（用户名、密码、确认密码）
- 登录页"记住密码"选项（30 天有效期）

### 服务端改进
- 服务启动时自动检测端口占用，显示占用进程信息和解决方案
- 服务启动时自动检测本机 IP 地址，显示局域网可访问地址
- 默认配置 `server.host` 改为 `0.0.0.0`，支持远程访问
- 修复 `biliobjclint-server restart` 命令无法正确重启服务的问题

### 重构
- 重构 `scripts/core/` 目录结构
  - lint 核心模块迁移至 `scripts/core/lint/`
  - 新增 `scripts/core/server/` 存放服务端代码
- 拆分 `server/cli.py` 为多个模块：db.py, auth.py, handlers.py, utils.py
- 拆分 `ui/templates.py` 为独立页面模块：styles.py, components.py, login.py, dashboard.py, users.py
- 更新所有规则文件的 import 路径（`core.*` → `core.lint.*`）

### 修复
- 修复 `claude/fixer.py` 重复的 elapsed 赋值语句
- 修复 `claude/cli.py` load_violations 返回值类型不一致

### 文档
- 新增 `LINTSERVER.md` 接口规范文档
- 更新 `docs/DEVELOPMENT.md` 添加服务端使用说明
- 更新 README 添加 `biliobjclint-server` 命令文档

## v1.3.7 (2026-02-03)

### 修复
- 修复后台升级时 Build Phase 更新失败的问题
  - 动态导入新版本模块前需将 scripts 目录加入 sys.path

## v1.3.6 (2026-02-03)

### 改进
- 将 `result_cache.json` 移至全局目录 `~/.biliobjclint/`
  - 减少目标 Xcode 工程中的生成文件
  - 缓存 key 为文件绝对路径 MD5，不同项目天然隔离

## v1.3.5 (2026-02-03)

### 重要
- 性能优化已完成：
- • 脚本执行优化: 49% 提升（单次执行输出双格式）
- • 规则结果缓存: 84% 提升（全量模式，跨编译复用）
- • 规则执行并行化: 8% 提升（受 Python GIL 限制）

### 修复
- 优化默认排除模式，支持任意深度目录匹配
  - `Vendor/**` → `**/Vendor/**`
  - `ThirdParty/**` → `**/ThirdParty/**`

## v1.3.4 (2026-02-03)

### 新增
- 新增规则结果缓存 (`result_cache.py`)
  - 将检查结果持久化到磁盘，跨编译复用
  - 缓存失效策略：文件 mtime 变化或规则配置 hash 变化
  - 仅全量模式生效，增量模式不使用
- 新增 `performance.result_cache_enabled` 配置项

## v1.3.3 (2026-02-03)

### 新增
- 添加本地开发调试模式 (`--debug PATH` 参数)
  - 支持在 Xcode 项目中直接测试本地开发代码，无需发布到 Homebrew
  - 使用 `.biliobjclint_debug` 标记文件持久化调试路径
  - 调试模式下跳过版本检查，避免覆盖本地代码
- 添加文件读取缓存 (`file_cache.py`)
  - 基于 mtime 的缓存失效策略
  - 线程安全，支持 LRU 淘汰
  - 可配置最大缓存容量
- 规则执行并行化支持
  - 使用 ThreadPoolExecutor 并行检查文件
  - 可配置线程数，默认自动检测
- 新增 `performance` 配置段
  - `parallel`: 启用/禁用并行执行
  - `max_workers`: 并行线程数
  - `file_cache_size_mb`: 缓存容量上限

### 改进
- 添加 Lint 检查耗时统计输出

### 文档
- 更新 DEVELOPMENT.md，添加本地调试章节
- 更新 CLAUDE.md，添加调试模式说明

## v1.3.2 (2026-02-03)

### 新增
- `commit.sh` 新增 `-i/--important` 参数
  - 支持多次调用，自动写入 CHANGELOG 的 `### 重要` 段落
  - 示例：`commit.sh -y -t feat -d "重大更新" -i "需要重新执行 --bootstrap"`
- 更新弹窗高亮显示重要提示
  - 解析 CHANGELOG 中的 `### 重要` 段落
  - 使用 ⚠️ emoji 和分隔线突出显示

## v1.3.1 (2026-02-03)

### 修复
- 修复 Package Manager Build Phase 模板仍使用不存在的 `WORKSPACE_PATH` 参数的问题
  - `bootstrap.sh` 已简化为直接从 Xcode 环境变量读取，无需传参

## v1.3.0 (2026-02-02)

### 重构
- 重新设计项目配置持久化方案
  - 新增 `project_config.py` 模块，替代 `scripts_path_utils.py`
  - 配置存储在 `~/.biliobjclint/projects.json`
  - Key 格式：`{xcodeproj_path}|{target_name}`（可通过 Xcode 的 `${PROJECT_FILE_PATH}` 和 `${TARGET_NAME}` 构建）
  - 存储完整项目配置：xcode_path、is_workspace、xcodeproj_path、project_name、target_name、scripts_dir_absolute、scripts_dir_relative

### 简化
- 简化 `bootstrap.sh`，直接从 Xcode 环境变量获取项目信息
  - 使用 `${PROJECT_FILE_PATH}` 和 `${TARGET_NAME}`（始终可用）
  - 移除复杂的参数解析逻辑
- `biliobjclint-xcode` 新增 `--xcodeproj` 参数，直接指定 .xcodeproj 路径

### 修复
- 彻底修复 scripts_path 配置查找失败的问题

## v1.2.5 (2026-02-02)

### 修复
- 修复 scripts_path 存储 key 使用 workspace 路径导致查找失败的问题
  - Xcode 环境变量中不存在 `WORKSPACE_PATH`，只有 `WORKSPACE_DIR`
  - 统一使用 `xcodeproj_path`（对应 `${PROJECT_FILE_PATH}`）作为存储 key
  - 确保 `--bootstrap` 保存和编译时查找使用相同的 key

## v1.2.4 (2026-02-02)

### 修复
- 修复 scripts_path 存储 key 不匹配问题
  - 使用 `realpath` (shell) 和 `Path.resolve()` (Python) 标准化路径
  - 支持绝对路径、相对路径、带尾部 `/` 的路径

## v1.2.3 (2026-02-02)

### 修复
- 修复 bootstrap.sh 在 workspace + xcodeproj 场景下未正确传递 project name 的问题
  - 从 `${PROJECT_FILE_PATH}` 自动提取项目名称作为 `-p` 参数

## v1.2.2 (2026-02-02)

### 修复
- 修复 `add_lint_phase()` 中 scripts_path 默认值计算错误的问题
  - `--bootstrap` 执行时自动计算并持久化 scripts 相对路径
  - 路径存储在 `~/.biliobjclint/scripts_paths.json`
  - 后续更新 Build Phase 时从持久化存储读取，确保路径一致

### 改进
- 增强 `copy_config` 日志输出，显示配置文件目标路径和状态

## v1.2.1 (2026-02-02)

### 修复
- **严重** 修复 `xcode_integrator.save()` 可能导致项目文件被清空的问题
  - 保存前创建备份文件
  - 保存后验证文件大小和格式
  - 异常时自动从备份恢复

## v1.2.0 (2026-02-02)

### 新增
- 新增 method_parameter 规则：检查方法参数数量
- Claude API 配置支持：api_base_url, api_token, api_key, model

### 重构
- 将 Code Style Check 脚本抽离为独立的 `code_style_check.sh`
- `--bootstrap` 模式只复制 `bootstrap.sh`，首次编译时动态注入 Code Style Check
- 移除主仓库 Formula 目录，Formula 只在 homebrew-biliobjclint tap 仓库维护
- 创建独立的 `background_upgrade.py` 脚本执行后台升级逻辑

### 后台升级流程
- 后台升级流程优化：先显示「正在更新」系统通知，再执行 brew upgrade
- 升级完成后显示弹窗，包含 CHANGELOG 更新内容
- 后台升级日志写入 `~/.biliobjclint/background_upgrade.log`
- 修复后台升级进程被 Xcode 终止的问题（使用独立子进程）
- 修复 brew upgrade 后 Build Phase 更新失败的问题（动态导入新版本模块）

### Build Phase 版本同步
- 每次编译时检查 Lint Phase 版本，版本不匹配时自动更新
- Build Phase 版本同步提示改为系统通知，不阻塞编译
- brew upgrade 完成后自动更新 Build Phase 到最新版本

### Lint 规则改进
- `method_length` 规则改进：增量模式下警告始终出现在方法定义行
- 新增 `Violation.related_lines` 属性，支持跨行范围的增量过滤

### 修复
- 修复 Lint Phase 检测逻辑误将 Package Manager phase 识别为 Lint Phase 的问题
- 修复 Xcode 沙盒环境中获取远端版本失败的问题
- 修复 `--manual` 使用自动计算的路径

### 开发工具
- commit.sh 支持 Conventional Commits 格式
- release.sh 支持非交互式模式 (-y/--yes)
- 添加 bootstrap 调试日志功能

## v1.1.16 (2026-01-30)

### 修复
- 修复 `_create_shell_script_phase` 中创建 phase 对象时未设置 `_id` 导致 pbxproj 排序失败的问题

## v1.1.15 (2026-01-30)

### 修复
- 修复 `_insert_phase_at_index` 中 PBXKey 类型转换错误导致 Build Phase 注入失败的问题

## v1.1.14 (2026-01-30)

### 重构
- 重构 rules 模块为子文件夹结构（base_rule/, memory_rules/, naming_rules/, security_rules/, style_rules/）
- 每个规则类独立为单独的 .py 文件，便于维护和扩展

### 改进
- 优化 Xcode Build Phase 注入逻辑
  - Package Manager 注入到 Build Phases 最前面（index 0）
  - Code Style Check 注入到 Package Manager 后面，若不存在则在 Compile Sources 前面
- 新增 `_find_phase_index()`、`_create_shell_script_phase()`、`_insert_phase_at_index()` 辅助方法

### 文档
- README 内置规则表格新增 3 个 memory_rules（wrapper_empty_pointer, dict_usage, collection_mutation）
- README bootstrap 脚本文档添加自动更新说明

### 其他
- 合并 test/ 到 tests/ 文件夹

## v1.1.13 (2026-01-30)

### 新增
- 新增 Homebrew 静默自动更新功能
- 新增 CHANGELOG.md 更新日志文件

### 改进
- bootstrap.sh 新增后台版本检测（通过 GitHub Tags API）
- 24小时检测间隔，不影响编译速度
- 静默执行更新，无弹窗干扰
- 更新完成后通过系统通知显示版本和更新内容

## v1.1.12 (2026-01-30)

### 修复
- 修复 WrapperEmptyPointerRule 无法检测多行字典字面量中值的问题
- 修复 DictUsageRule 正则表达式无法匹配含空格值的问题
- 修复 CollectionMutationRule 对 Elvis 运算符和三目运算符 key 的误报

### 改进
- 新增 `_find_dict_key_value_in_line()` 方法支持多行容器检测
- 新增 `_check_ternary_safe_key()` 方法识别安全的 key 表达式
- 优化 setObject:forKey: 检测模式，支持值中包含空格

## v1.1.11 (2026-01-28)

### 修复
- 修复 DictUsageRule 和 CollectionMutationRule 的 check 方法参数名不匹配问题

## v1.1.10 (2026-01-28)

### 新增
- 新增 WrapperEmptyPointerRule 规则，检测容器字面量中的空指针风险
- 新增 DictUsageRule 规则，检测 setObject:forKey: 的使用
- 新增 CollectionMutationRule 规则，检测集合修改操作的安全性

### 改进
- 优化三目运算符和 Elvis 运算符的安全性检测

## v1.1.9 (2026-01-27)

### 新增
- 新增 biliobjclint-xcode --bootstrap 模式，支持自动复制 bootstrap.sh 并注入 Build Phase

## v1.1.8 (2026-01-27)

### 改进
- 优化 Xcode 集成脚本
- 改进 Build Phase 注入逻辑

## v1.1.0 (2026-01-20)

### 新增
- 首个正式版本发布
- 支持通过 Homebrew 安装
- 支持 Xcode Build Phase 集成
- 支持增量检查（仅检查 git 变更）
- 支持 Claude AI 自动修复
- 内置多种代码规范检查规则
