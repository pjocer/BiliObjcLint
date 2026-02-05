"""
Method Length Rule - 方法长度检查
"""
import re
from typing import List, Set, Tuple

from ..base_rule import BaseRule
from ..rule_utils import find_matching_brace
from core.lint.reporter import Violation, ViolationType


# SubType 定义
class SubType:
    """method_length 规则的子类型"""
    TOO_LONG = ViolationType("too_long", "方法 '{method}' 共 {length} 行，超过限制 {max_lines} 行")


class MethodLengthRule(BaseRule):
    """方法长度检查"""

    identifier = "method_length"
    name = "Method Length Check"
    description = "检查方法是否超过最大行数"
    display_name = "方法长度"
    default_severity = "warning"

    # 方法声明模式
    METHOD_START_PATTERN = re.compile(r'^[-+]\s*\([^)]+\)')
    # 方法名提取模式
    METHOD_NAME_PATTERN = re.compile(r'^[-+]\s*\([^)]+\)\s*([a-zA-Z_][a-zA-Z0-9_:]*)')

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        max_lines = self.get_param("max_lines", 80)
        line_num = 1

        while line_num <= len(lines):
            line = lines[line_num - 1]

            # 检测方法开始
            if self.METHOD_START_PATTERN.match(line.strip()):
                method_start_line = line_num

                # 提取方法名
                match = self.METHOD_NAME_PATTERN.search(line.strip())
                method_name = match.group(1) if match else "unknown"

                # 通过 get_related_lines 获取方法范围
                related_lines = self.get_related_lines(file_path, method_start_line, lines)
                method_end_line = related_lines[1]
                method_length = method_end_line - method_start_line + 1

                if method_length > max_lines:
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=method_start_line,
                        column=1,
                        lines=lines,
                        violation_type=SubType.TOO_LONG,
                        related_lines=related_lines,
                        message_vars={"method": method_name, "length": str(method_length), "max_lines": str(max_lines)}
                    ))

                # 跳到方法结束行之后继续扫描
                line_num = method_end_line + 1
            else:
                line_num += 1

        return violations

    def get_related_lines(self, file_path: str, line: int, lines: List[str]) -> Tuple[int, int]:
        """
        获取方法范围

        从方法声明行到匹配的闭合大括号
        """
        method_end = find_matching_brace(lines, line, '{', '}')
        return (line, method_end)
