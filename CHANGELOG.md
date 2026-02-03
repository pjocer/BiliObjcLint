# BiliObjCLint 更新日志

所有重要的版本更新都会记录在此文件中。

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
