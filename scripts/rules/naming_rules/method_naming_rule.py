"""
Method Naming Rule - 方法命名检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.reporter import Violation


class MethodNamingRule(BaseRule):
    """方法命名检查"""

    identifier = "method_naming"
    name = "Method Naming Check"
    description = "检查方法命名是否符合小驼峰规范"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 匹配方法声明
        # - (void)doSomething;
        # + (instancetype)sharedInstance;
        pattern = r'^[-+]\s*\([^)]+\)\s*([a-zA-Z_][a-zA-Z0-9_]*)'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 去除注释
            code_line = line.split('//')[0]

            match = re.search(pattern, code_line)
            if match:
                method_name = match.group(1)

                # 方法名应以小写字母开头
                if method_name and method_name[0].isupper():
                    # 跳过 init 系列方法的特殊情况
                    if not method_name.startswith('init'):
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=match.start(1) + 1,
                            message=f"方法名 '{method_name}' 应以小写字母开头"
                        ))

        return violations
