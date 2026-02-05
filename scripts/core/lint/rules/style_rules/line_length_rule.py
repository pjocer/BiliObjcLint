"""
Line Length Rule - 行长度检查
"""
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation, ViolationType


# SubType 定义
class SubType:
    """line_length 规则的子类型"""
    TOO_LONG = ViolationType("too_long", "行长度 {length} 超过限制 {max_length}")


class LineLengthRule(BaseRule):
    """行长度检查"""

    identifier = "line_length"
    name = "Line Length Check"
    description = "检查代码行是否超过最大长度"
    display_name = "行长度"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        max_length = self.get_param("max_length", 120)
        tab_width = self.get_param("tab_width", 4)  # 制表符宽度，默认 4 空格

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 忽略 URL 和 import 语句
            if 'http://' in line or 'https://' in line:
                continue
            if line.strip().startswith('#import') or line.strip().startswith('@import'):
                continue

            # 计算视觉长度（展开制表符）
            visual_length = self._calculate_visual_length(line, tab_width)

            if visual_length > max_length:
                related_lines = self.get_related_lines(file_path, line_num, lines)
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=max_length + 1,
                    lines=lines,
                    violation_type=SubType.TOO_LONG,
                    related_lines=related_lines,
                    message_vars={"length": str(visual_length), "max_length": str(max_length)}
                ))

        return violations

    def _calculate_visual_length(self, line: str, tab_width: int) -> int:
        """
        计算行的视觉长度（展开制表符）

        制表符会对齐到下一个 tab_width 的倍数位置
        """
        visual_length = 0
        for char in line:
            if char == '\t':
                # 制表符对齐到下一个 tab_width 倍数
                visual_length += tab_width - (visual_length % tab_width)
            else:
                visual_length += 1
        return visual_length
