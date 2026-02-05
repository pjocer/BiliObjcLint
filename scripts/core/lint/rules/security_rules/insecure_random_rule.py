"""
Insecure Random Rule - 不安全随机数检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation


class InsecureRandomRule(BaseRule):
    """不安全随机数检查"""

    identifier = "insecure_random"
    name = "Insecure Random Check"
    description = "检测不安全的随机数生成方式"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 不安全的随机数 API
        insecure_patterns = [
            (r'\brand\s*\(\s*\)', "rand() 不安全，请使用 arc4random()"),
            (r'\brandom\s*\(\s*\)', "random() 不安全，请使用 arc4random()"),
            (r'\bdrand48\s*\(\s*\)', "drand48() 不安全，请使用 arc4random()"),
            (r'\bsrand\s*\(', "srand() 用于初始化不安全的随机数生成器，请改用 arc4random()"),
        ]

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 获取 related_lines（单行）
            related_lines = self.get_related_lines(file_path, line_num, lines)

            for pattern, message in insecure_patterns:
                if re.search(pattern, line):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=1,
                        message=message,
                        lines=lines,
                        related_lines=related_lines
                    ))

        return violations
