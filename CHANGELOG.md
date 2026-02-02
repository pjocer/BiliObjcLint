# BiliObjCLint 更新日志

所有重要的版本更新都会记录在此文件中。

## v1.1.44 (2026-02-02)

### 测试
- 测试编译时检测版本不匹配并自动同步 Build Phase 版本

## v1.1.43 (2026-02-02)

### 修复
- 更新弹窗 CHANGELOG 格式优化：移除 markdown 标题符号，只显示更新项
- 修复后台升级日志丢失问题：日志直接写入 `~/.biliobjclint/background_upgrade.log`

## v1.1.42 (2026-02-02)

### 测试
- 测试后台升级流程和 CHANGELOG 显示

## v1.1.41 (2026-02-02)

### 修复
- 修复更新弹窗不显示 CHANGELOG 内容的问题
  - CHANGELOG.md 被 Homebrew 自动提取到 Cellar 根目录，而非 libexec
  - 修正 `get_changelog_for_version()` 函数的文件路径查找逻辑

## v1.1.40 (2026-02-02)

### 修复
- 修复 CHANGELOG.md 未被安装到 brew prefix 的问题
- 增强后台升级调试日志，记录所有参数到 `~/.biliobjclint/background_upgrade.log`

### 文档
- 在 DEVELOPMENT.md 中添加 Homebrew 安装后日志文件位置说明

## v1.1.39 (2026-02-02)

### 测试
- 测试后台升级流程

## v1.1.38 (2026-02-02)

### 修复
- 修复后台升级进程无法正确执行的问题
  - 使用 venv Python 替代系统 Python，确保 pbxproj 等依赖可用
  - 使用 shlex.quote 正确转义路径参数，避免空格导致参数解析失败
  - 增强日志输出，便于问题排查

## v1.1.37 (2026-02-02)

### 修复
- 修复后台升级时「正在更新」通知延迟显示的问题（现在立即显示）
- 修复 brew upgrade 后 Build Phase 版本号未更新的问题（使用动态导入新版本模块）

## v1.1.36 (2026-02-02)

### 改进
- 优化后台升级流程：brew update 后先显示「正在更新」系统通知，再执行 brew upgrade
- 升级完成后按顺序执行：复制脚本 → 更新 Build Phase → 显示完成弹窗
- 完成弹窗显示 CHANGELOG 内容，用户点击 OK 后进程结束

## v1.1.35 (2026-02-02)

### 改进
- Build Phase 版本同步提示改为系统通知，不再阻塞编译

## v1.1.34 (2026-02-02)

### 修复
- 修复 brew upgrade 完成后 Build Phase 版本号不更新的问题
- brew upgrade 完成后自动更新 Build Phase 到最新版本
- 修复弹窗被 Xcode 中断时的 KeyboardInterrupt 异常

### 改进
- 添加 CHANGELOG 读取调试日志，便于排查问题

## v1.1.33 (2026-02-02)

### 改进
- Build Phase 版本更新时弹出提示弹窗，显示版本号变更信息

### 修复
- 修复弹窗互斥逻辑：brew 更新时只弹一次更新完成弹窗，不重复弹出版本同步弹窗

## v1.1.32 (2026-02-02)

### 修复
- 修复升级后 Build Phase 版本号不更新的问题
- 每次编译时检查 Lint Phase 版本，版本不匹配时自动更新

### 改进
- 更新弹窗现在正确显示 CHANGELOG 内容

## v1.1.31 (2026-02-02)

### 重构
- 移除主仓库 Formula 目录，Formula 只在 homebrew-biliobjclint tap 仓库维护
- 简化 release.sh 发布流程，tag 现在只包含源代码变更

## v1.1.30 (2026-02-02)

### 修复
- 修复后台升级线程被强制终止导致 brew upgrade 无法执行的问题
- 创建独立的 `background_upgrade.py` 脚本执行升级逻辑
- 使用 `subprocess.Popen` 替代 `daemon=True` 的线程
- 使用 `start_new_session=True` 确保子进程独立于父进程

## v1.1.29 (2026-02-02)

### 修复
- 修复 `--manual` 使用自动计算的路径

## v1.1.28 (2026-02-02)

### 重构
- 将 Code Style Check 脚本抽离为独立的 `code_style_check.sh`
- `--bootstrap` 模式只复制 `bootstrap.sh`，首次编译时动态注入 Code Style Check
- 简化 Build Phase 脚本，改为调用外部脚本文件
- 更新 `--manual` 帮助文档，提供清晰的手动配置步骤

### 改进
- `bootstrap.sh` 首次运行时自动复制 `code_style_check.sh` 到项目 scripts 目录
- `code_style_check.sh` 通过 `brew --prefix` 自动定位 biliobjclint 安装路径
- 支持 Homebrew 安装方式，无需硬编码路径

## v1.1.27 (2026-02-02)

### 修复
- 修复更新弹窗不显示 CHANGELOG 内容的问题
- 从本地 brew 安装目录读取 CHANGELOG.md，避免网络请求
- 修复 AWK 脚本对 `### ` 子标题的解析

## v1.1.26 (2026-02-02)

### 修复
- 修复 Xcode 沙盒环境中获取远端版本失败的问题
- 优先使用 brew info 获取远端版本
- 将 brew update 移到版本检查阶段

## v1.1.25 (2026-02-02)

### 改进
- 迁移 release 文档到 RELEASE.md
- 添加 bootstrap 调试日志功能

## v1.1.24 (2026-02-02)

### 改进
- 优化 commit.sh 和 release.sh 脚本文档
- 添加典型开发流程说明

## v1.1.23 (2026-02-02)

### 改进
- commit.sh 支持 Conventional Commits 格式
- 新增交互式输入和 CLI 参数支持

## v1.1.22 (2026-02-02)

### 改进
- release.sh 支持非交互式模式 (-y/--yes)
- 修复 Homebrew tap 同步冲突问题

## v1.1.21 (2026-02-02)

### 新增
- 新增 method_parameter 规则：检查方法参数数量
- Claude API 配置支持：api_base_url, api_token, api_key, model

## v1.1.20 (2026-02-02)

### 修复
- 修复 Lint Phase 检测逻辑误将 Package Manager phase 识别为 Lint Phase 的问题
- 修复 bootstrap 流程中 Package Manager phase 被错误移除的问题

## v1.1.19 (2026-02-02)

### 改进
- `method_length` 规则警告现在始终出现在方法定义行，而不是变更起始行
- 新增 `Violation.related_lines` 属性，支持跨行范围的增量过滤
- 增量模式下，只要方法内有任何代码改动，就会检查整个方法的总行数

## v1.1.18 (2026-02-02)

### 修复
- 修复自动更新检测时状态文件过早保存的问题（网络失败时不再保存，下次继续尝试）
- 修复后台更新进程可能被 Xcode 提前终止的问题（使用 disown 脱离父进程）

### 改进
- 更新完成通知改为弹窗对话框，可显示完整 CHANGELOG 内容
- README 补充状态文件 `~/.biliobjclint_update_state` 的说明

## v1.1.17 (2026-02-02)

### 修复
- 修复 `method_length` 规则在增量模式下被全局过滤器错误过滤的问题
- 增量模式下，违规现在报告在方法内第一个变更行，避免被过滤

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
