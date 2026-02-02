"""
Rule Engine Module - Python 规则引擎
"""
import os
import sys
import importlib.util
from pathlib import Path
from typing import List, Dict, Set, Type, Optional, Tuple
from abc import ABC, abstractmethod

from .reporter import Violation, Severity
from .config import RuleConfig
from .logger import get_logger


class BaseRule(ABC):
    """规则基类"""

    # 子类必须定义
    identifier: str = ""
    name: str = ""
    description: str = ""
    default_severity: str = "warning"

    def __init__(self, config: Optional[RuleConfig] = None):
        self.config = config or RuleConfig()
        self.severity = Severity(self.config.severity if self.config else self.default_severity)

    @property
    def enabled(self) -> bool:
        return self.config.enabled if self.config else True

    def get_param(self, key: str, default=None):
        """获取配置参数"""
        if self.config and self.config.params:
            return self.config.params.get(key, default)
        return default

    @abstractmethod
    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        """
        执行规则检查

        Args:
            file_path: 文件路径
            content: 文件完整内容
            lines: 文件按行分割的列表
            changed_lines: 变更的行号集合（空集合表示检查全部）
        Returns:
            违规列表
        """
        pass

    def should_check_line(self, line_num: int, changed_lines: Set[int]) -> bool:
        """判断是否应该检查该行"""
        if not changed_lines:
            return True
        return line_num in changed_lines

    def create_violation(self, file_path: str, line: int, column: int, message: str,
                         related_lines: Optional[Tuple[int, int]] = None) -> Violation:
        """
        创建违规记录

        Args:
            file_path: 文件路径
            line: 违规行号
            column: 违规列号
            message: 违规消息
            related_lines: 关联行范围 (start, end)，用于增量过滤时判断是否保留
        """
        return Violation(
            file_path=file_path,
            line=line,
            column=column,
            severity=self.severity,
            message=message,
            rule_id=self.identifier,
            source='biliobjclint',
            related_lines=related_lines
        )


class RuleEngine:
    """规则引擎 - 管理和执行规则"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.rules: List[BaseRule] = []
        self.logger = get_logger("biliobjclint")
        self.logger.debug(f"RuleEngine initialized: project_root={project_root}")

    def load_builtin_rules(self, rules_config: Dict[str, RuleConfig]):
        """加载内置规则"""
        self.logger.debug("Loading builtin rules...")

        # 动态导入 rules 模块
        scripts_dir = Path(__file__).parent.parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        from rules import get_all_rules

        loaded_count = 0
        for rule_class in get_all_rules():
            rule_id = rule_class.identifier
            config = rules_config.get(rule_id, RuleConfig())

            if config.enabled:
                rule = rule_class(config)
                self.rules.append(rule)
                loaded_count += 1
                self.logger.debug(f"Loaded rule: {rule_id} (severity={config.severity})")
            else:
                self.logger.debug(f"Skipped disabled rule: {rule_id}")

        self.logger.info(f"Loaded {loaded_count} builtin rules")

    def load_custom_rules(self, custom_rules_path: str):
        """加载自定义 Python 规则"""
        rules_dir = self.project_root / custom_rules_path
        self.logger.debug(f"Loading custom rules from: {rules_dir}")

        if not rules_dir.exists():
            self.logger.debug("Custom rules directory does not exist")
            return

        loaded_count = 0
        for py_file in rules_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            try:
                self._load_rule_from_file(py_file)
                loaded_count += 1
                self.logger.debug(f"Loaded custom rule from: {py_file.name}")
            except Exception as e:
                self.logger.warning(f"Failed to load custom rule {py_file}: {e}")
                print(f"Warning: Failed to load custom rule {py_file}: {e}", file=sys.stderr)

        self.logger.info(f"Loaded {loaded_count} custom rules")

    def _load_rule_from_file(self, file_path: Path):
        """从文件加载规则"""
        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        module = importlib.util.module_from_spec(spec)

        # 添加 scripts 目录到 path
        scripts_dir = self.project_root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        spec.loader.exec_module(module)

        # 查找 BaseRule 的子类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and
                issubclass(attr, BaseRule) and
                attr is not BaseRule and
                hasattr(attr, 'identifier') and
                attr.identifier):
                rule = attr()
                self.rules.append(rule)

    def check_file(self, file_path: str, changed_lines: Set[int] = None) -> List[Violation]:
        """
        对单个文件执行所有规则检查

        Args:
            file_path: 文件路径
            changed_lines: 变更行号集合（None 表示检查全部）
        Returns:
            违规列表
        """
        violations = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
        except Exception as e:
            return violations

        for rule in self.rules:
            if not rule.enabled:
                continue

            try:
                rule_violations = rule.check(
                    file_path=file_path,
                    content=content,
                    lines=lines,
                    changed_lines=changed_lines or set()
                )
                violations.extend(rule_violations)
            except Exception as e:
                print(f"Warning: Rule {rule.identifier} failed on {file_path}: {e}", file=sys.stderr)

        return violations

    def check_files(self, files: List[str], changed_lines_map: Dict[str, Set[int]] = None) -> List[Violation]:
        """
        对多个文件执行检查

        Args:
            files: 文件路径列表
            changed_lines_map: {file_path: changed_lines_set}
        Returns:
            所有违规列表
        """
        self.logger.info(f"Checking {len(files)} files with {len(self.rules)} rules")
        all_violations = []

        for i, file_path in enumerate(files):
            changed_lines = changed_lines_map.get(file_path, set()) if changed_lines_map else None
            violations = self.check_file(file_path, changed_lines)
            all_violations.extend(violations)
            if violations:
                self.logger.debug(f"File {i+1}/{len(files)} ({Path(file_path).name}): {len(violations)} violations")

        self.logger.info(f"Total violations found: {len(all_violations)}")
        return all_violations
