"""
Method Naming Rule - 方法命名检查
"""
import re
from typing import List, Set, Tuple

from ..base_rule import BaseRule
from ..rule_utils import strip_line_comment
from core.lint.reporter import Violation


class MethodNamingRule(BaseRule):
    """方法命名检查"""

    identifier = "method_naming"
    name = "Method Naming Check"
    description = "检查方法命名是否符合小驼峰规范"
    default_severity = "warning"

    # 方法声明模式
    METHOD_PATTERN = re.compile(r'^[-+]\s*\([^)]+\)\s*([a-zA-Z_][a-zA-Z0-9_]*)')

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 去除注释
            code_line = strip_line_comment(line)

            match = self.METHOD_PATTERN.search(code_line)
            if match:
                method_name = match.group(1)

                # 方法名应以小写字母开头
                if method_name and method_name[0].isupper():
                    # 跳过 init 系列方法的特殊情况
                    if not method_name.startswith('init'):
                        related_lines = self.get_related_lines(file_path, line_num, lines)
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=match.start(1) + 1,
                            message=f"方法名 '{method_name}' 应以小写字母开头",
                            related_lines=related_lines
                        ))

        return violations

    def get_related_lines(self, file_path: str, line: int, lines: List[str]) -> Tuple[int, int]:
        """
        获取方法声明范围

        从方法定义行到 ; 或 {
        """
        for i in range(line - 1, min(len(lines), line + 20)):
            code_line = strip_line_comment(lines[i])
            if ';' in code_line or '{' in code_line:
                return (line, i + 1)
        return (line, line)
