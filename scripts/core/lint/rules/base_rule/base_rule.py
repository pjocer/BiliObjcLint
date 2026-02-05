"""
Base Rule - 规则基类
"""
from abc import ABC, abstractmethod
from typing import List, Set, Optional, Tuple
import sys

# 添加路径以便导入
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.lint.reporter import Violation, Severity
from core.lint.config import RuleConfig


class BaseRule(ABC):
    """
    规则基类

    所有自定义规则都应该继承此类并实现 check 方法
    """

    # 子类必须定义的属性
    identifier: str = ""       # 规则唯一标识符，如 "class_prefix"
    name: str = ""             # 规则名称，如 "Class Prefix Check"
    description: str = ""      # 规则描述
    default_severity: str = "warning"  # 默认严重级别: warning | error

    def __init__(self, config: Optional[RuleConfig] = None):
        """
        初始化规则

        Args:
            config: 规则配置，包含 enabled、severity、params
        """
        self.config = config or RuleConfig()

        # 确定严重级别
        # 如果配置中显式指定了 severity，使用配置值；否则使用规则的 default_severity
        severity_str = config.severity if (config and config.severity) else self.default_severity
        try:
            self.severity = Severity(severity_str)
        except ValueError:
            self.severity = Severity.WARNING

    @property
    def enabled(self) -> bool:
        """规则是否启用"""
        return self.config.enabled if self.config else True

    def get_param(self, key: str, default=None):
        """
        获取配置参数

        Args:
            key: 参数名
            default: 默认值
        Returns:
            参数值
        """
        if self.config and self.config.params:
            return self.config.params.get(key, default)
        return default

    @abstractmethod
    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        """
        执行规则检查

        Args:
            file_path: 文件绝对路径
            content: 文件完整内容
            lines: 文件按行分割的列表（从索引 0 开始）
            changed_lines: 变更的行号集合（行号从 1 开始，空集合表示检查全部）
        Returns:
            违规列表
        """
        pass

    def should_check_line(self, line_num: int, changed_lines: Set[int]) -> bool:
        """
        判断是否应该检查该行

        Args:
            line_num: 行号（从 1 开始）
            changed_lines: 变更行号集合
        Returns:
            是否应该检查
        """
        if not changed_lines:
            return True
        return line_num in changed_lines

    def get_related_lines(self, file_path: str, line: int, lines: List[str]) -> Tuple[int, int]:
        """
        获取关联行范围（子类覆写）

        审查范围定义了规则需要扫描和关联的代码范围。
        注意：审查范围 ≠ 问题位置
        - related_lines 是审查范围 (start_line, end_line)
        - violation.line 是具体出问题的行号
        - 约束：related_lines.start <= violation.line <= related_lines.end

        Args:
            file_path: 文件路径
            line: 当前检测的行号（1-indexed）
            lines: 文件所有行

        Returns:
            (start_line, end_line): 1-indexed, inclusive
        """
        # 默认单行
        return (line, line)

    def create_violation(self, file_path: str, line: int, column: int, message: str,
                         related_lines: Optional[Tuple[int, int]] = None) -> Violation:
        """
        创建违规记录

        Args:
            file_path: 文件路径
            line: 行号（从 1 开始）
            column: 列号（从 1 开始）
            message: 违规消息
            related_lines: 关联行范围 (start, end)，用于增量过滤时判断是否保留
        Returns:
            Violation 对象
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

    def create_violation_with_severity(self, file_path: str, line: int, column: int,
                                       message: str, severity: Severity,
                                       related_lines: Optional[Tuple[int, int]] = None) -> Violation:
        """
        创建带自定义 severity 的违规记录

        用于需要覆盖默认 severity 的场景（如同一规则中不同级别的问题）。

        Args:
            file_path: 文件路径
            line: 行号（从 1 开始）
            column: 列号（从 1 开始）
            message: 违规消息
            severity: 严重级别
            related_lines: 关联行范围 (start, end)
        Returns:
            Violation 对象
        """
        return Violation(
            file_path=file_path,
            line=line,
            column=column,
            severity=severity,
            message=message,
            rule_id=self.identifier,
            source='biliobjclint',
            related_lines=related_lines
        )

    def get_hash_context(self, file_path: str, line: int, lines: List[str],
                         violation: Violation) -> Tuple[int, int]:
        """
        获取用于计算 code_hash 的代码范围

        优先使用 violation 中已有的 related_lines 字段，
        如果没有则调用 get_related_lines() 方法计算。

        不同规则可以覆盖此方法以定义不同的哈希上下文范围：
        - 单行规则（默认）：仅哈希违规所在行
        - Block 范围规则：哈希整个 Block
        - 方法范围规则：哈希整个方法
        - 文件头规则：哈希前 N 行

        Args:
            file_path: 文件路径
            line: 违规行号（1-indexed）
            lines: 文件所有行
            violation: 违规对象（可获取 related_lines 等信息）

        Returns:
            (start_line, end_line): 1-indexed, inclusive
        """
        # 优先使用 violation 中的 related_lines
        if violation.related_lines:
            return violation.related_lines
        # 否则调用 get_related_lines 计算
        return self.get_related_lines(file_path, line, lines)

    def get_hash_context_value(self, file_path: str, line: int, lines: List[str],
                               violation: Violation) -> Optional[str]:
        """
        获取 violation 的代码内容哈希值

        调用 get_hash_context() 获取代码范围，然后使用 violation_hash 模块计算哈希。

        Args:
            file_path: 文件路径
            line: 违规行号（1-indexed）
            lines: 文件所有行
            violation: 违规对象

        Returns:
            MD5 哈希字符串（16 字符），计算失败返回 None
        """
        from core.lint.violation_hash import compute_hash_from_range

        if not lines:
            return None

        try:
            # 获取哈希范围
            start, end = self.get_hash_context(file_path, line, lines, violation)
            # 使用 violation_hash 模块计算哈希
            return compute_hash_from_range(violation.rule_id, lines, start, end)
        except Exception:
            return None

    def __repr__(self):
        return f"<{self.__class__.__name__} identifier={self.identifier} enabled={self.enabled}>"
