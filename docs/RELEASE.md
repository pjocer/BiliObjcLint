# Release Guide

本文档面向 BiliObjCLint 的维护者，介绍如何发布新版本。

## 发布新版本

使用 release 脚本自动发布：

```bash
# 自动递增 patch 版本 (v1.0.0 -> v1.0.1)
./scripts/others/release.sh

# 自动递增 minor 版本 (v1.0.0 -> v1.1.0)
./scripts/others/release.sh minor

# 自动递增 major 版本 (v1.0.0 -> v2.0.0)
./scripts/others/release.sh major

# 指定版本号
./scripts/others/release.sh v1.2.3
```

脚本会自动完成以下操作：
1. 检查是否有未提交的更改
2. 创建并推送 git tag
3. 计算 release tarball 的 SHA256
4. 更新 Homebrew Formula
5. 提交并推送更改

## 版本号规范

遵循 [Semantic Versioning](https://semver.org/)：

| 变更类型 | 版本升级 | 示例 |
|----------|----------|------|
| Bug 修复 | Patch | v1.0.0 → v1.0.1 |
| 新功能（向后兼容） | Minor | v1.0.0 → v1.1.0 |
| 破坏性变更 | Major | v1.0.0 → v2.0.0 |

## 手动发布流程

如果需要手动发布（不使用脚本）：

```bash
# 1. 确保所有更改已提交
git status

# 2. 创建并推送标签
git tag v1.1.0
git push origin v1.1.0

# 3. 计算 SHA256
curl -sL https://github.com/pjocer/BiliObjcLint/archive/refs/tags/v1.1.0.tar.gz | shasum -a 256

# 4. 更新 Formula/biliobjclint.rb
# - 修改 url 中的版本号
# - 更新 sha256 值

# 5. 提交 Formula 更新
git add Formula/biliobjclint.rb
git commit -m "Bump version to v1.1.0"
git push
```

## Homebrew Formula 说明

Formula 文件位于 `Formula/biliobjclint.rb`，包含：

- `url`: 指向 GitHub release tarball
- `sha256`: tarball 的校验和
- `depends_on`: Python 依赖
- `install`: 安装步骤
- `test`: 安装后测试

## 用户更新方式

发布后，用户可通过以下方式更新：

```bash
brew update && brew upgrade biliobjclint
```
