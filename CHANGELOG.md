# BiliObjCLint 更新日志

所有重要的版本更新都会记录在此文件中。

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
