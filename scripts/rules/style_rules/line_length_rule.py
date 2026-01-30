"""
Line Length Rule - 行长度检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.reporter import Violation


class LineLengthRule(BaseRule):
    """行长度检查"""

    identifier = "line_length"
    name = "Line Length Check"
    description = "检查代码行是否超过最大长度"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        max_length = self.get_param("max_length", 120)

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 忽略 URL 和 import 语句
            if 'http://' in line or 'https://' in line:
                continue
            if line.strip().startswith('#import') or line.strip().startswith('@import'):
                continue

            line_length = len(line)
            if line_length > max_length:
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=max_length + 1,
                    message=f"行长度 {line_length} 超过限制 {max_length}"
                ))

        return violations
