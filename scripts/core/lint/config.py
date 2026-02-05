"""
Configuration Module - 配置文件解析和管理
"""
import copy
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from .logger import get_logger


@dataclass
class RuleConfig:
    """规则配置"""
    enabled: bool = True
    severity: Optional[str] = None  # None 表示使用规则的 default_severity
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClaudeAutofixConfig:
    """Claude 自动修复配置"""
    # 触发模式: any | error | disable
    trigger: str = "any"
    # 执行模式: silent | terminal | vscode
    mode: str = "silent"
    # 超时时间（秒）
    timeout: int = 120
    # API 基础地址（内部网关地址，留空则使用官方 API）
    api_base_url: str = ""
    # API 认证令牌（用于内部网关，对应 ANTHROPIC_AUTH_TOKEN）
    api_token: str = ""
    # API 密钥（用于官方 API，对应 ANTHROPIC_API_KEY）
    api_key: str = ""
    # Claude 模型名称
    model: str = ""
    # 是否禁用非必要的网络请求
    disable_nonessential_traffic: bool = True


@dataclass
class LocalPodsConfig:
    """本地 Pod 检测配置"""
    # 是否启用本地 Pod 检测
    enabled: bool = True
    # 是否对本地 Pod 进行增量检测
    # - True: 只检查本地 Pod 的 git 变更（如果是 git 仓库）
    # - False: 全量检查本地 Pod 的所有文件（推荐，因为本地 Pod 通常是正在开发的代码）
    incremental: bool = False
    # 本地 Pod 的包含模式（空表示所有）
    included_pods: List[str] = field(default_factory=list)
    # 本地 Pod 的排除模式
    excluded_pods: List[str] = field(default_factory=lambda: ["*Test*", "*Mock*"])


@dataclass
class PerformanceConfig:
    """性能优化配置"""
    # 是否启用并行检查
    parallel: bool = True
    # 最大工作线程数（0 表示自动：min(32, cpu_count * 2)）
    max_workers: int = 0
    # 文件缓存最大容量（MB）
    file_cache_size_mb: int = 100
    # 是否启用规则结果缓存（持久化到磁盘，跨进程复用）
    result_cache_enabled: bool = True


@dataclass
class MetricsConfig:
    """统计上报配置"""
    enabled: bool = False
    endpoint: str = "http://127.0.0.1:18080"
    token: str = ""
    project_key: str = ""
    project_name: str = ""
    mode: str = "push"
    spool_dir: str = "~/.biliobjclint/metrics_spool"
    timeout_ms: int = 2000
    retry_max: int = 3


@dataclass
class LintConfig:
    """完整的 Lint 配置"""
    # 基础配置
    base_branch: str = "origin/master"
    incremental: bool = True
    fail_on_error: bool = True

    # 文件过滤
    included: List[str] = field(default_factory=lambda: ["**/*.m", "**/*.mm", "**/*.h"])
    excluded: List[str] = field(default_factory=lambda: ["Pods/**", "Vendor/**"])

    # Python 规则配置
    python_rules: Dict[str, RuleConfig] = field(default_factory=dict)

    # 自定义规则路径
    custom_rules_python_path: str = "./custom_rules/python/"

    # Claude 自动修复配置
    claude_autofix: ClaudeAutofixConfig = field(default_factory=ClaudeAutofixConfig)

    # 统计上报配置
    metrics: MetricsConfig = field(default_factory=MetricsConfig)

    # 本地 Pod 检测配置
    local_pods: LocalPodsConfig = field(default_factory=LocalPodsConfig)

    # 性能优化配置
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)


class ConfigLoader:
    """配置加载器"""

    DEFAULT_CONFIG = {
        "base_branch": "origin/master",
        "incremental": True,
        "fail_on_error": True,
        "included": ["**/*.m", "**/*.mm", "**/*.h"],
        "excluded": ["Pods/**", "Vendor/**", "ThirdParty/**", "**/Generated/**"],
        "python_rules": {
            "class_prefix": {
                "enabled": True,
                "severity": "warning",
                "params": {"prefix": ""}  # 空表示不检查
            },
            "weak_delegate": {
                "enabled": True,
                "severity": "error"
            },
            "block_retain_cycle": {
                "enabled": True,
                "severity": "warning"
            },
            "method_length": {
                "enabled": True,
                "severity": "warning",
                "params": {"max_lines": 80}
            },
            "line_length": {
                "enabled": True,
                "severity": "warning",
                "params": {"max_length": 120}
            },
            "forbidden_api": {
                "enabled": False,
                "severity": "error",
                "params": {"apis": []}
            },
            "todo_fixme": {
                "enabled": True,
                "severity": "warning"
            },
            "force_unwrap": {
                "enabled": True,
                "severity": "warning"
            }
        },
        "custom_rules": {
            "python": {
                "enabled": True,
                "path": "./custom_rules/python/"
            }
        },
        "claude_autofix": {
            "trigger": "any",
            "mode": "silent",
            "timeout": 120
        },
        "metrics": {
            "enabled": False,
            "endpoint": "http://127.0.0.1:18080",
            "token": "",
            "project_key": "",
            "project_name": "",
            "mode": "push",
            "spool_dir": "~/.biliobjclint/metrics_spool",
            "timeout_ms": 2000,
            "retry_max": 3
        },
        "local_pods": {
            "enabled": True,
            "incremental": False,
            "included_pods": [],
            "excluded_pods": ["*Test*", "*Mock*"]
        },
        "performance": {
            "parallel": True,
            "max_workers": 0,
            "file_cache_size_mb": 100
        }
    }

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else None
        self._config: Dict[str, Any] = {}
        self.logger = get_logger("biliobjclint")

    def load(self) -> LintConfig:
        """加载配置文件"""
        self.logger.debug(f"Loading config from: {self.config_path}")

        # 从默认配置开始（深拷贝）
        self._config = copy.deepcopy(self.DEFAULT_CONFIG)

        # 如果有配置文件，合并配置
        if self.config_path and self.config_path.exists():
            self.logger.debug(f"Config file exists, loading user config")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f) or {}
            self._merge_config(self._config, user_config)
            self.logger.debug(f"Merged {len(user_config)} user config keys")
        else:
            self.logger.debug("No config file found, using defaults only")

        config = self._build_lint_config()
        self.logger.debug(f"Config built: {len(config.python_rules)} python rules enabled")
        return config

    def _merge_config(self, base: Dict, override: Dict):
        """递归合并配置"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def _build_lint_config(self) -> LintConfig:
        """构建 LintConfig 对象"""
        python_rules = {}
        for rule_name, rule_cfg in self._config.get("python_rules", {}).items():
            if isinstance(rule_cfg, dict):
                python_rules[rule_name] = RuleConfig(
                    enabled=rule_cfg.get("enabled", True),
                    severity=rule_cfg.get("severity", "warning"),
                    params=rule_cfg.get("params", {})
                )

        custom_rules = self._config.get("custom_rules", {})

        claude_autofix_cfg = self._config.get("claude_autofix", {})
        claude_autofix = ClaudeAutofixConfig(
            trigger=claude_autofix_cfg.get("trigger", "any"),
            mode=claude_autofix_cfg.get("mode", "silent"),
            timeout=claude_autofix_cfg.get("timeout", 120),
            api_base_url=claude_autofix_cfg.get("api_base_url", ""),
            api_token=claude_autofix_cfg.get("api_token", ""),
            api_key=claude_autofix_cfg.get("api_key", ""),
            model=claude_autofix_cfg.get("model", ""),
            disable_nonessential_traffic=claude_autofix_cfg.get("disable_nonessential_traffic", True)
        )

        metrics_cfg = self._config.get("metrics", {})
        metrics = MetricsConfig(
            enabled=metrics_cfg.get("enabled", False),
            endpoint=metrics_cfg.get("endpoint", "http://127.0.0.1:18080"),
            token=metrics_cfg.get("token", ""),
            project_key=metrics_cfg.get("project_key", ""),
            project_name=metrics_cfg.get("project_name", ""),
            mode=metrics_cfg.get("mode", "push"),
            spool_dir=metrics_cfg.get("spool_dir", "~/.biliobjclint/metrics_spool"),
            timeout_ms=metrics_cfg.get("timeout_ms", 2000),
            retry_max=metrics_cfg.get("retry_max", 3)
        )

        local_pods_cfg = self._config.get("local_pods", {})
        local_pods = LocalPodsConfig(
            enabled=local_pods_cfg.get("enabled", True),
            incremental=local_pods_cfg.get("incremental", False),
            included_pods=local_pods_cfg.get("included_pods", []),
            excluded_pods=local_pods_cfg.get("excluded_pods", ["*Test*", "*Mock*"])
        )

        performance_cfg = self._config.get("performance", {})
        performance = PerformanceConfig(
            parallel=performance_cfg.get("parallel", True),
            max_workers=performance_cfg.get("max_workers", 0),
            file_cache_size_mb=performance_cfg.get("file_cache_size_mb", 100),
            result_cache_enabled=performance_cfg.get("result_cache_enabled", True)
        )

        return LintConfig(
            base_branch=self._config.get("base_branch", "origin/master"),
            incremental=self._config.get("incremental", True),
            fail_on_error=self._config.get("fail_on_error", True),
            included=self._config.get("included", ["**/*.m", "**/*.mm", "**/*.h"]),
            excluded=self._config.get("excluded", []),
            python_rules=python_rules,
            custom_rules_python_path=custom_rules.get("python", {}).get("path", "./custom_rules/python/"),
            claude_autofix=claude_autofix,
            metrics=metrics,
            local_pods=local_pods,
            performance=performance
        )

    def get_raw_config(self) -> Dict[str, Any]:
        """获取原始配置字典"""
        return self._config
