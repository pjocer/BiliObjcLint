"""
TODO/FIXME Rule - TODO/FIXME 检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation


class TodoFixmeRule(BaseRule):
    """TODO/FIXME 检查"""

    identifier = "todo_fixme"
    name = "TODO/FIXME Check"
    description = "检测代码中的 TODO 和 FIXME 注释"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 匹配 TODO、FIXME、HACK、XXX 等标记
        pattern = r'(?://|/\*|\*)\s*(TODO|FIXME|HACK|XXX|BUG)[\s:]*(.{0,50})'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                tag = match.group(1).upper()
                desc = match.group(2).strip() if match.group(2) else ""

                message = f"发现 {tag} 标记"
                if desc:
                    message += f": {desc}"

                related_lines = self.get_related_lines(file_path, line_num, lines)
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=match.start() + 1,
                    message=message,
                    related_lines=related_lines
                ))

        return violations
