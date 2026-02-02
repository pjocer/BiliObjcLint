"""
Method Parameter Rule - 方法参数数量检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.reporter import Violation


class MethodParameterRule(BaseRule):
    """方法参数数量检查"""

    identifier = "method_parameter"
    name = "Method Parameter Count Check"
    description = "检查方法参数数量是否超过限制"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []
        max_params = self.get_param("max_params", 4)

        # 检测方法声明行（以 - 或 + 开头）
        method_start_pattern = r'^[-+]\s*\([^)]+\)'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 去除注释
            code_line = line.split('//')[0]

            # 检查是否是方法定义行
            if re.match(method_start_pattern, code_line.strip()):
                # 计算参数数量：统计该行中冒号的数量
                param_count = code_line.count(':')

                if param_count > max_params:
                    # 提取方法选择器名（去除参数类型和参数名）
                    # 例如: "- (void)t:(BOOL)t f:(BOOL)f" -> "t:f:"
                    selector_parts = re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*):', code_line)
                    method_selector = ':'.join(selector_parts) + ':' if selector_parts else 'unknown'

                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=1,
                        message=f"方法 '{method_selector}' 有 {param_count} 个参数，超过限制 {max_params} 个"
                    ))

        return violations
