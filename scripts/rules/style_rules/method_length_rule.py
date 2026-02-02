"""
Method Length Rule - 方法长度检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.reporter import Violation


class MethodLengthRule(BaseRule):
    """方法长度检查"""

    identifier = "method_length"
    name = "Method Length Check"
    description = "检查方法是否超过最大行数"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        max_lines = self.get_param("max_lines", 80)

        # 简单的方法检测：匹配方法开始和结束
        method_start_pattern = r'^[-+]\s*\([^)]+\)'
        brace_count = 0
        in_method = False
        method_start_line = 0
        method_name = ""

        for line_num, line in enumerate(lines, 1):
            # 检测方法开始
            if re.match(method_start_pattern, line.strip()):
                in_method = True
                method_start_line = line_num
                brace_count = 0

                # 提取方法名
                match = re.search(r'^[-+]\s*\([^)]+\)\s*([a-zA-Z_][a-zA-Z0-9_:]*)', line.strip())
                if match:
                    method_name = match.group(1)

            if in_method:
                brace_count += line.count('{') - line.count('}')

                # 方法结束
                if brace_count <= 0 and '{' in content[sum(len(l)+1 for l in lines[:method_start_line]):]:
                    method_length = line_num - method_start_line + 1
                    method_end_line = line_num

                    if method_length > max_lines:
                        # 始终在方法定义行报告违规，设置 related_lines 为方法范围
                        # 增量过滤时会检查 related_lines 与 changed_lines 是否有交集
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=method_start_line,
                            column=1,
                            message=f"方法 '{method_name}' 共 {method_length} 行，超过限制 {max_lines} 行",
                            related_lines=(method_start_line, method_end_line)
                        ))

                    in_method = False

        return violations
