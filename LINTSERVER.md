# BiliObjCLint 本地服务接口规范（LINTSERVER）

本规范定义 `biliobjclint-server` 提供的本地服务接口、鉴权方式与数据上报格式。

## 1. 服务配置

默认配置文件：
- `~/.biliobjclint/biliobjclint_server_config.json`

配置模板：
- `config/biliobjclint_server_config.json`

主要配置项：
- `server.host` / `server.port`
- `auth.enabled` / `auth.admin_user` / `auth.admin_password`
- `ingest.token`
- `ingest.spool_path`
- `storage.type` / `storage.path` / `storage.retention_days`
- `logging.level` / `logging.path`

## 2. 启动方式

```bash
# Homebrew 安装后入口（由 formula wrapper 提供）
biliobjclint-server start
biliobjclint-server restart

# 直接运行脚本
scripts/bin/biliobjclint-server.sh --start
scripts/bin/biliobjclint-server.sh --restart

# Homebrew Services
brew services start biliobjclint-server
brew services stop biliobjclint-server
```

## 3. 鉴权方式

- 如果 `ingest.token` 为空：允许匿名上报
- 如果 `ingest.token` 非空：请求头需包含 `X-BiliObjCLint-Token: <token>`

## 4. 接口定义

### 4.1 健康检查

- **GET** `/healthz`

响应示例：
```json
{ "status": "ok" }
```

### 4.2 统计上报

- **POST** `/api/v1/ingest`

说明：
- 服务端以 `run_id` 为主键进行 upsert
- 允许分阶段上报：可先上报 lint 结果，后续仅携带 `autofix` 更新

请求头：
```
Content-Type: application/json
X-BiliObjCLint-Token: <token>   # 可选，取决于服务端配置
```

请求体（JSON）：

```json
{
  "schema_version": "1.1",
  "run_id": "uuid-xxxx",
  "created_at": "2026-02-04T12:30:12+08:00",

  "project": {
    "key": "OneSDK-iOS",
    "name": "OneSDK-iOS"
  },

  "tool": {
    "name": "biliobjclint",
    "version": "v1.3.3"
  },

  "summary": {
    "total": 100,
    "warning": 60,
    "error": 40
  },

  "rules": {
    "method_naming": { "count": 12, "severity": "warning", "enabled": true }
  },

  "autofix": {
    "enabled": true,
    "trigger": "any",
    "mode": "silent",
    "triggered": true,
    "flow": "dialog",
    "decision": "fix",
    "cli_available": true,

    "actions": [
      {
        "type": "fix_all",
        "target_count": 100,
        "result": "success",
        "elapsed_ms": 8123,
        "message": "Fix completed"
      }
    ],

    "summary": {
      "attempts": 1,
      "success": 1,
      "failed": 0,
      "cancelled": 0,
      "target_total": 100
    }
  },

  "config_snapshot": {
    "base_branch": "",
    "incremental": true,
    "fail_on_error": true,
    "included": ["**/*.m", "**/*.mm", "**/*.h"],
    "excluded": ["Pods/**", "**/Vendor/**"],
    "claude_autofix": {
      "trigger": "any",
      "mode": "silent",
      "timeout": 120,
      "disable_nonessential_traffic": true
    },
    "metrics": {
      "enabled": true,
      "endpoint": "http://127.0.0.1:18080",
      "token": "",
      "project_key": "OneSDK-iOS",
      "mode": "push",
      "spool_dir": "~/.biliobjclint/metrics_spool",
      "timeout_ms": 2000,
      "retry_max": 3
    }
  }
}
```

响应示例：
```json
{ "success": true }
```

错误响应示例：
```json
{ "error": "unauthorized" }
```

## 5. 结果落库与展示

- 服务端负责解析 `rules` 与 `autofix` 统计字段并写入数据库
- 不保存源代码、文件路径或具体片段
- 数据按 `project.key` + 时间维度聚合

## 6. 版本兼容

- `schema_version` 用于兼容字段变化
- 服务端应允许未知字段并忽略
