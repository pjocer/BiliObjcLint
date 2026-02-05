"""
Insecure Random Rule - 不安全随机数检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation, ViolationType


# SubType 定义
class SubType:
    """insecure_random 规则的子类型"""
    RAND = ViolationType("rand", "rand() 不安全，请使用 arc4random()")
    RANDOM = ViolationType("random", "random() 不安全，请使用 arc4random()")
    DRAND48 = ViolationType("drand48", "drand48() 不安全，请使用 arc4random()")
    SRAND = ViolationType("srand", "srand() 用于初始化不安全的随机数生成器，请改用 arc4random()")


class InsecureRandomRule(BaseRule):
    """不安全随机数检查"""

    identifier = "insecure_random"
    name = "Insecure Random Check"
    description = "检测不安全的随机数生成方式"
    display_name = "不安全随机数"
    default_severity = "warning"

    # 不安全的随机数 API (pattern, sub_type)
    INSECURE_PATTERNS = [
        (r'\brand\s*\(\s*\)', SubType.RAND),
        (r'\brandom\s*\(\s*\)', SubType.RANDOM),
        (r'\bdrand48\s*\(\s*\)', SubType.DRAND48),
        (r'\bsrand\s*\(', SubType.SRAND),
    ]

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 获取 related_lines（单行）
            related_lines = self.get_related_lines(file_path, line_num, lines)

            for pattern, violation_type in self.INSECURE_PATTERNS:
                if re.search(pattern, line):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=1,
                        lines=lines,
                        violation_type=violation_type,
                        related_lines=related_lines
                    ))

        return violations
