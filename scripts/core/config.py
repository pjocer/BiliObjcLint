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
    severity: str = "warning"  # warning | error
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OCLintConfig:
    """OCLint 配置"""
    enabled: bool = True
    enable_rules: List[str] = field(default_factory=list)
    disable_rules: List[str] = field(default_factory=list)
    rule_configurations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ClaudeAutofixConfig:
    """Claude 自动修复配置"""
    # 触发模式: any | error | disable
    trigger: str = "any"
    # 执行模式: silent | terminal | vscode
    mode: str = "silent"
    # 超时时间（秒）
    timeout: int = 120


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

    # OCLint 配置
    oclint: OCLintConfig = field(default_factory=OCLintConfig)

    # Python 规则配置
    python_rules: Dict[str, RuleConfig] = field(default_factory=dict)

    # 自定义规则路径
    custom_rules_python_path: str = "./custom_rules/python/"
    custom_rules_cpp_enabled: bool = True

    # 严重级别映射
    severity_mapping: Dict[str, str] = field(default_factory=lambda: {
        "priority1": "error",
        "priority2": "warning",
        "priority3": "warning"
    })

    # Claude 自动修复配置
    claude_autofix: ClaudeAutofixConfig = field(default_factory=ClaudeAutofixConfig)


class ConfigLoader:
    """配置加载器"""

    DEFAULT_CONFIG = {
        "base_branch": "origin/master",
        "incremental": True,
        "fail_on_error": True,
        "included": ["**/*.m", "**/*.mm", "**/*.h"],
        "excluded": ["Pods/**", "Vendor/**", "ThirdParty/**", "**/Generated/**"],
        "oclint": {
            "enabled": True,
            "enable_rules": [],
            "disable_rules": [],
            "rule_configurations": [
                {"key": "LONG_METHOD", "value": 80},
                {"key": "LONG_LINE", "value": 120},
                {"key": "CYCLOMATIC_COMPLEXITY", "value": 10},
                {"key": "NPATH_COMPLEXITY", "value": 200},
                {"key": "LONG_VARIABLE_NAME", "value": 30},
                {"key": "SHORT_VARIABLE_NAME", "value": 2},
            ]
        },
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
            },
            "cpp": {
                "enabled": True
            }
        },
        "severity_mapping": {
            "priority1": "error",
            "priority2": "warning",
            "priority3": "warning"
        },
        "claude_autofix": {
            "trigger": "any",
            "mode": "silent",
            "timeout": 120
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
        oclint_cfg = self._config.get("oclint", {})
        oclint = OCLintConfig(
            enabled=oclint_cfg.get("enabled", True),
            enable_rules=oclint_cfg.get("enable_rules", []),
            disable_rules=oclint_cfg.get("disable_rules", []),
            rule_configurations=oclint_cfg.get("rule_configurations", [])
        )

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
            timeout=claude_autofix_cfg.get("timeout", 120)
        )

        return LintConfig(
            base_branch=self._config.get("base_branch", "origin/master"),
            incremental=self._config.get("incremental", True),
            fail_on_error=self._config.get("fail_on_error", True),
            included=self._config.get("included", ["**/*.m", "**/*.mm", "**/*.h"]),
            excluded=self._config.get("excluded", []),
            oclint=oclint,
            python_rules=python_rules,
            custom_rules_python_path=custom_rules.get("python", {}).get("path", "./custom_rules/python/"),
            custom_rules_cpp_enabled=custom_rules.get("cpp", {}).get("enabled", True),
            severity_mapping=self._config.get("severity_mapping", {}),
            claude_autofix=claude_autofix
        )

    def get_raw_config(self) -> Dict[str, Any]:
        """获取原始配置字典"""
        return self._config
