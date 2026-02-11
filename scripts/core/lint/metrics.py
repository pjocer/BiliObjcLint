"""
Metrics Module - 统计汇总与上报
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import LintConfig, MetricsConfig, RuleConfig
from lib.logger import get_logger
from lib.common.project_store import get_project_key, get_project_name
from .reporter import Reporter, Severity, Violation


SCHEMA_VERSION = "1.2"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _read_version(project_root: Path) -> str:
    version_file = project_root / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return "unknown"


def _sanitize_config_snapshot(raw: Dict[str, Any]) -> Dict[str, Any]:
    data = json.loads(json.dumps(raw)) if raw else {}
    data.pop("python_rules", None)

    claude_cfg = data.get("claude_autofix")
    if isinstance(claude_cfg, dict):
        claude_cfg.pop("api_key", None)
        claude_cfg.pop("api_token", None)
        claude_cfg.pop("api_base_url", None)
        data["claude_autofix"] = claude_cfg

    metrics_cfg = data.get("metrics")
    if isinstance(metrics_cfg, dict):
        metrics_cfg.pop("token", None)
        data["metrics"] = metrics_cfg

    return data


def _build_violations_list(violations: Iterable[Violation], project_root: Path) -> List[Dict[str, Any]]:
    """构建违规列表（基于 Violation.to_dict()，转换为相对路径）"""
    result = []
    for v in violations:
        # 使用 to_dict() 获取基础数据
        item = v.to_dict()

        # 转换为相对路径并使用 "file" 作为 key（metrics 兼容格式）
        try:
            rel_path = str(Path(v.file_path).relative_to(project_root))
        except ValueError:
            rel_path = v.file_path

        del item["file_path"]
        item["file"] = rel_path

        # metrics 上报不需要这些字段
        item.pop("source", None)
        item.pop("pod_name", None)
        # 保留 context 和 related_lines 用于 Server 详情页显示

        result.append(item)
    return result


def _build_rules_summary(
    violations: Iterable[Violation],
    rule_configs: Dict[str, RuleConfig],
    rule_display_info: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Dict[str, Any]]:
    counts: Dict[str, int] = {}
    severities: Dict[str, str] = {}
    rule_display_info = rule_display_info or {}

    for v in violations:
        counts[v.rule_id] = counts.get(v.rule_id, 0) + 1
        if v.rule_id not in severities:
            severities[v.rule_id] = v.severity.value

    rules: Dict[str, Dict[str, Any]] = {}

    for rule_id, cfg in rule_configs.items():
        info = rule_display_info.get(rule_id, {})
        rules[rule_id] = {
            "count": counts.get(rule_id, 0),
            "severity": cfg.severity,
            "enabled": cfg.enabled,
            "rule_name": info.get("display_name", ""),
            "description": info.get("description", ""),
        }

    for rule_id, count in counts.items():
        if rule_id in rules:
            continue
        info = rule_display_info.get(rule_id, {})
        rules[rule_id] = {
            "count": count,
            "severity": severities.get(rule_id, "warning"),
            "enabled": True,
            "rule_name": info.get("display_name", ""),
            "description": info.get("description", ""),
        }

    return rules


def _build_autofix_stub(config: LintConfig, violations: Iterable[Violation]) -> Dict[str, Any]:
    violations = list(violations)
    trigger = config.claude_autofix.trigger
    enabled = trigger != "disable"
    triggered = False
    if enabled:
        if trigger == "any":
            triggered = len(violations) > 0
        elif trigger == "error":
            triggered = any(v.severity == Severity.ERROR for v in violations)

    return {
        "enabled": enabled,
        "trigger": trigger,
        "mode": config.claude_autofix.mode,
        "triggered": triggered,
        "flow": "none",
        "decision": "pending",
        "cli_available": None,
        "actions": [],
        "summary": {
            "attempts": 0,
            "success": 0,
            "failed": 0,
            "cancelled": 0,
            "target_total": 0,
        },
    }


def build_lint_payload(
    run_id: str,
    config: LintConfig,
    raw_config: Dict[str, Any],
    reporter: Reporter,
    project_root: Path,
    duration_ms: int,
    started_at_iso: Optional[str] = None,
    rule_display_info: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Any]:
    created_at = started_at_iso or _now_iso()
    project_key_val = get_project_key(fallback=project_root.name)
    project_name_val = get_project_name(fallback=project_root.name)
    tool_version = _read_version(project_root)

    summary = {
        "total": len(reporter.violations),
        "warning": sum(1 for v in reporter.violations if v.severity == Severity.WARNING),
        "error": sum(1 for v in reporter.violations if v.severity == Severity.ERROR),
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "project": {
            "key": project_key_val,
            "name": project_name_val,
        },
        "tool": {
            "name": "biliobjclint",
            "version": tool_version,
        },
        "summary": summary,
        "rules": _build_rules_summary(reporter.violations, config.python_rules, rule_display_info),
        "violations": _build_violations_list(reporter.violations, project_root),
        "autofix": _build_autofix_stub(config, reporter.violations),
        "config_snapshot": _sanitize_config_snapshot(raw_config),
        "duration_ms": duration_ms,
    }
    return payload


def build_autofix_payload(
    run_id: str,
    config: MetricsConfig,
    project_key: str,
    project_name: str,
    tool_version: str,
    autofix: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": _now_iso(),
        "project": {
            "key": project_key_val,
            "name": project_name_val,
        },
        "tool": {
            "name": "biliobjclint",
            "version": tool_version,
        },
        "autofix": autofix,
    }


def _endpoint_url(endpoint: str) -> str:
    if endpoint.endswith("/api/v1/ingest"):
        return endpoint
    if endpoint.endswith("/"):
        return endpoint + "api/v1/ingest"
    return endpoint + "/api/v1/ingest"


def _spool_path(metrics_cfg: MetricsConfig) -> Path:
    base = Path(str(metrics_cfg.spool_dir)).expanduser()
    if base.suffix == ".jsonl":
        return base
    return base / "metrics_spool.jsonl"


def _post_payload(metrics_cfg: MetricsConfig, payload: Dict[str, Any], logger) -> bool:
    url = _endpoint_url(metrics_cfg.endpoint)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if metrics_cfg.token:
        headers["X-BiliObjCLint-Token"] = metrics_cfg.token

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    timeout = max(metrics_cfg.timeout_ms / 1000.0, 0.5)

    for _ in range(max(metrics_cfg.retry_max, 1)):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if 200 <= resp.status < 300:
                    return True
        except Exception as e:
            logger.debug(f"Metrics post failed: {e}")
            time.sleep(0.1)
    return False


def _flush_spool(metrics_cfg: MetricsConfig, logger) -> None:
    spool_path = _spool_path(metrics_cfg)
    if not spool_path.exists():
        return

    lines = spool_path.read_text(encoding="utf-8").splitlines()
    remaining = []

    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not _post_payload(metrics_cfg, payload, logger):
            remaining.append(line)

    if remaining:
        spool_path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
    else:
        spool_path.unlink(missing_ok=True)


def send_payload(payload: Dict[str, Any], metrics_cfg: MetricsConfig, logger=None) -> None:
    logger = logger or get_logger("biliobjclint")
    if not metrics_cfg.enabled:
        logger.debug("Metrics disabled, skip send")
        return
    if not metrics_cfg.endpoint:
        logger.debug("Metrics endpoint empty, skip send")
        return

    _flush_spool(metrics_cfg, logger)
    if _post_payload(metrics_cfg, payload, logger):
        logger.info("Metrics payload sent")
        return

    spool_path = _spool_path(metrics_cfg)
    spool_path.parent.mkdir(parents=True, exist_ok=True)
    with spool_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    logger.warning(f"Metrics payload spooled: {spool_path}")
