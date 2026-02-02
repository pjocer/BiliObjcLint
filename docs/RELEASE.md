# Release Guide

本文档面向 BiliObjCLint 的版本发布流程。

## 发布脚本

### release.sh

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

## 典型开发流程

```bash
# 1. 开发完成后，提交改动
./scripts/others/commit.sh -t feat -s "规则" -d "新增 xxx 规则"

# 2. 发布新版本
./scripts/others/release.sh -y

# 或者非交互式一键完成
./scripts/others/commit.sh -y -t feat -d "新增功能" && ./scripts/others/release.sh -y
```

## 版本管理

### 版本文件

版本号存储在 `VERSION` 文件中（不含 v 前缀），如：
```
1.1.24
```

Git tag 使用带 v 前缀的版本号，如 `v1.1.24`。

### 版本号规则

遵循 [Semantic Versioning](https://semver.org/)：
- **MAJOR**: 不兼容的 API 修改
- **MINOR**: 向下兼容的功能新增
- **PATCH**: 向下兼容的问题修复

### Homebrew 分发

通过 Homebrew tap 仓库分发：
- Tap 仓库: `pjocer/biliobjclint`
- Formula: `Formula/biliobjclint.rb`

发布脚本会自动：
1. 计算新版本 tarball 的 SHA256
2. 更新本仓库的 Formula
3. 同步到 tap 仓库

用户更新命令：
```bash
brew update && brew upgrade biliobjclint
```
