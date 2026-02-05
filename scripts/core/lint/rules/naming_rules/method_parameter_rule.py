"""
Method Parameter Rule - 方法参数数量检查
"""
import re
from typing import List, Set, Tuple

from ..base_rule import BaseRule
from ..rule_utils import strip_line_comment
from core.lint.reporter import Violation, ViolationType


# SubType 定义
class SubType:
    """method_parameter 规则的子类型"""
    TOO_MANY_PARAMS = ViolationType(
        "too_many_params",
        "方法 '{method}' 有 {count} 个参数，超过限制 {max} 个"
    )


class MethodParameterRule(BaseRule):
    """方法参数数量检查"""

    identifier = "method_parameter"
    name = "Method Parameter Count Check"
    description = "检查方法参数数量是否超过限制"
    display_name = "参数数量"
    default_severity = "warning"

    # 方法声明模式
    METHOD_START_PATTERN = re.compile(r'^[-+]\s*\([^)]+\)')

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []
        max_params = self.get_param("max_params", 4)

        line_num = 1
        while line_num <= len(lines):
            line = lines[line_num - 1]

            # 去除注释
            code_line = strip_line_comment(line)

            # 检查是否是方法定义行
            if self.METHOD_START_PATTERN.match(code_line.strip()):
                method_start = line_num
                # 通过 get_related_lines 获取方法声明范围
                related_lines = self.get_related_lines(file_path, method_start, lines)
                method_end = related_lines[1]

                # 合并多行方法声明
                full_declaration = ' '.join(
                    strip_line_comment(lines[i]) for i in range(method_start - 1, method_end)
                )

                # 计算参数数量：统计冒号数量
                param_count = full_declaration.count(':')

                if param_count > max_params:
                    # 提取方法选择器名
                    selector_parts = re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*):', full_declaration)
                    method_selector = ':'.join(selector_parts) + ':' if selector_parts else 'unknown'

                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=method_start,
                        column=1,
                        lines=lines,
                        violation_type=SubType.TOO_MANY_PARAMS,
                        related_lines=related_lines,
                        message_vars={"method": method_selector, "count": str(param_count), "max": str(max_params)}
                    ))

                line_num = method_end + 1
            else:
                line_num += 1

        return violations

    def _find_method_declaration_end(self, lines: List[str], start_line: int) -> int:
        """
        查找方法声明的结束行

        方法声明以 ; 或 { 结束
        """
        for i in range(start_line - 1, min(len(lines), start_line + 20)):
            code_line = strip_line_comment(lines[i])
            if ';' in code_line or '{' in code_line:
                return i + 1
        return start_line

    def get_related_lines(self, file_path: str, line: int, lines: List[str]) -> Tuple[int, int]:
        """
        获取方法声明范围

        从方法定义行到 ; 或 {
        """
        method_end = self._find_method_declaration_end(lines, line)
        return (line, method_end)
