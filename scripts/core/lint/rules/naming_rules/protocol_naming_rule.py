"""
Protocol Naming Rule - 协议命名检查
"""
import re
from typing import List, Set, Tuple

from ..base_rule import BaseRule
from core.lint.reporter import Violation, ViolationType


# SubType 定义
class SubType:
    """protocol_naming 规则的子类型"""
    MISSING_PREFIX = ViolationType(
        "missing_prefix",
        "协议 '{protocol}' 应使用指定前缀（{prefixes}）"
    )


class ProtocolNamingRule(BaseRule):
    """协议命名检查"""

    identifier = "protocol_naming"
    name = "Protocol Naming Check"
    description = "检查协议命名是否使用指定前缀"
    display_name = "协议命名"
    default_severity = "warning"

    # @protocol XXXDelegate <NSObject>
    PROTOCOL_PATTERN = re.compile(r'@protocol\s+([A-Za-z_][A-Za-z0-9_]*)\s*[<;]')

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 获取配置的前缀列表
        prefixes = self.get_param("prefixes", [])

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 跳过注释行
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            # 检测协议声明
            match = self.PROTOCOL_PATTERN.search(line)
            if match:
                protocol_name = match.group(1)

                # 检查前缀
                if prefixes:
                    has_valid_prefix = any(protocol_name.startswith(prefix) for prefix in prefixes)
                    if not has_valid_prefix:
                        prefixes_str = ', '.join(prefixes)
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=match.start(1) + 1,
                            lines=lines,
                            violation_type=SubType.MISSING_PREFIX,
                            related_lines=self.get_related_lines(file_path, line_num, lines),
                            message_vars={"protocol": protocol_name, "prefixes": prefixes_str}
                        ))

        return violations

    def get_related_lines(self, file_path: str, line: int, lines: List[str]) -> Tuple[int, int]:
        """
        获取协议声明范围

        从 @protocol 到 > 或 ;
        """
        start = line
        for i in range(line - 1, min(len(lines), line + 5)):
            if '>' in lines[i] or ';' in lines[i]:
                return (start, i + 1)
        return (start, start)
