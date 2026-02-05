"""
Base Rule - 规则基类
"""
from abc import ABC, abstractmethod
from typing import List, Set, Optional, Tuple, Dict
import sys

# 添加路径以便导入
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.lint.reporter import Violation, Severity, ViolationType
from core.lint.config import RuleConfig
from ..rule_utils import compute_context_hash


class BaseRule(ABC):
    """
    规则基类

    所有自定义规则都应该继承此类并实现 check 方法
    """

    # 子类必须定义的属性
    identifier: str = ""       # 规则唯一标识符，如 "class_prefix"
    name: str = ""             # 规则名称，如 "Class Prefix Check"
    description: str = ""      # 规则描述
    display_name: str = ""     # 规则中文名称（用于 UI 显示），如 "类名前缀"
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

    def get_context(self, lines: List[str], related_lines: Tuple[int, int]) -> str:
        """
        提取关联行的代码内容

        Args:
            lines: 文件所有行
            related_lines: 关联行范围 (start, end)，1-indexed, inclusive

        Returns:
            代码内容（保留缩进和换行）
        """
        start, end = related_lines
        # 边界检查
        start = max(1, start)
        end = min(len(lines), end)
        # 提取代码（保留缩进，去除行尾空白）
        context_lines = lines[start - 1:end]  # 转为 0-indexed
        return '\n'.join(line.rstrip() for line in context_lines)

    def compute_code_hash(self, context: str) -> str:
        """
        计算代码内容哈希（不含 rule_id）

        Args:
            context: 归一化后的代码内容

        Returns:
            MD5 哈希字符串（16 字符）
        """
        return compute_context_hash(context)

    def create_violation(self, file_path: str, line: int, column: int,
                         lines: List[str], violation_type: ViolationType,
                         related_lines: Optional[Tuple[int, int]] = None,
                         message_vars: Optional[Dict[str, str]] = None) -> Violation:
        """
        创建违规记录（一次性确定所有属性）

        Args:
            file_path: 文件路径
            line: 行号（从 1 开始）
            column: 列号（从 1 开始）
            lines: 文件所有行（用于计算 context 和 code_hash）
            violation_type: 违规类型（包含 sub_type、message 模板、severity）
            related_lines: 关联行范围 (start, end)，不传则自动计算
            message_vars: message 模板中的变量替换，如 {"var": "self"}
        Returns:
            Violation 对象（所有属性不可变）
        """
        # 1. 确定 related_lines
        if related_lines is None:
            related_lines = self.get_related_lines(file_path, line, lines)

        # 2. 提取 context
        context = self.get_context(lines, related_lines)

        # 3. 计算 code_hash（不含 rule_id）
        code_hash = self.compute_code_hash(context)

        # 4. 格式化 message（替换占位符）
        message = violation_type.message
        if message_vars:
            message = message.format(**message_vars)

        return Violation(
            file_path=file_path,
            line=line,
            column=column,
            severity=violation_type.severity,
            message=message,
            rule_id=self.identifier,
            source='biliobjclint',
            related_lines=related_lines,
            context=context,
            code_hash=code_hash,
            sub_type=violation_type.id,
            rule_name=self.display_name or None
        )

    def __repr__(self):
        return f"<{self.__class__.__name__} identifier={self.identifier} enabled={self.enabled}>"
