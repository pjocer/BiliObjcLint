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

                    if method_length > max_lines:
                        # 检查方法内是否有变更
                        if not changed_lines:
                            # 全量模式：在方法起始行报告
                            report_line = method_start_line
                            violations.append(self.create_violation(
                                file_path=file_path,
                                line=report_line,
                                column=1,
                                message=f"方法 '{method_name}' 共 {method_length} 行，超过限制 {max_lines} 行"
                            ))
                        else:
                            # 增量模式：找到方法内第一个变更行
                            changed_in_method = [
                                l for l in range(method_start_line, line_num + 1)
                                if l in changed_lines
                            ]
                            if changed_in_method:
                                report_line = changed_in_method[0]
                                violations.append(self.create_violation(
                                    file_path=file_path,
                                    line=report_line,
                                    column=1,
                                    message=f"方法 '{method_name}' 共 {method_length} 行，超过限制 {max_lines} 行（方法定义在第 {method_start_line} 行）"
                                ))
                            # 方法内没有变更，跳过不报告

                    in_method = False

        return violations
