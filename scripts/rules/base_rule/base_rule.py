"""
Base Rule - 规则基类
"""
from abc import ABC, abstractmethod
from typing import List, Set, Optional
import sys

# 添加路径以便导入
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.reporter import Violation, Severity
from core.config import RuleConfig


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
        severity_str = self.config.severity if self.config else self.default_severity
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

    def create_violation(self, file_path: str, line: int, column: int, message: str) -> Violation:
        """
        创建违规记录

        Args:
            file_path: 文件路径
            line: 行号（从 1 开始）
            column: 列号（从 1 开始）
            message: 违规消息
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
            source='biliobjclint'
        )

    def __repr__(self):
        return f"<{self.__class__.__name__} identifier={self.identifier} enabled={self.enabled}>"
