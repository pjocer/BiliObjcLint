"""
TODO/FIXME Rule - TODO/FIXME 检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation, ViolationType


# SubType 定义
class SubType:
    """todo_fixme 规则的子类型"""
    TODO = ViolationType("todo", "发现 TODO 标记{desc}")
    FIXME = ViolationType("fixme", "发现 FIXME 标记{desc}")
    HACK = ViolationType("hack", "发现 HACK 标记{desc}")
    XXX = ViolationType("xxx", "发现 XXX 标记{desc}")
    BUG = ViolationType("bug", "发现 BUG 标记{desc}")


# Tag 名称到 SubType 的映射
_TAG_SUBTYPE_MAP = {
    "TODO": SubType.TODO,
    "FIXME": SubType.FIXME,
    "HACK": SubType.HACK,
    "XXX": SubType.XXX,
    "BUG": SubType.BUG,
}


class TodoFixmeRule(BaseRule):
    """TODO/FIXME 检查"""

    identifier = "todo_fixme"
    name = "TODO/FIXME Check"
    description = "检测代码中的 TODO 和 FIXME 注释"
    display_name = "待办事项"
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

                # 获取对应的 ViolationType
                violation_type = _TAG_SUBTYPE_MAP.get(tag, SubType.TODO)

                # 格式化描述
                desc_str = f": {desc}" if desc else ""

                related_lines = self.get_related_lines(file_path, line_num, lines)
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=match.start() + 1,
                    lines=lines,
                    violation_type=violation_type,
                    related_lines=related_lines,
                    message_vars={"desc": desc_str}
                ))

        return violations
