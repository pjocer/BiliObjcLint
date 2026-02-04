"""
Constant Naming Rule - 常量命名检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation


class ConstantNamingRule(BaseRule):
    """常量命名检查"""

    identifier = "constant_naming"
    name = "Constant Naming Check"
    description = "检查常量命名是否符合规范"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 匹配 #define 宏常量（全大写）
        define_pattern = r'#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+'

        # 匹配 const 常量
        const_pattern = r'(?:static\s+)?(?:const\s+)?\w+\s*\*?\s*(?:const\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*='

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 检查 #define
            match = re.search(define_pattern, line)
            if match:
                const_name = match.group(1)

                # 跳过函数宏
                if '(' in line[match.end():match.end()+1]:
                    continue

                # 跳过小写字母开头的宏（通常是函数式宏或特殊用途）
                if const_name[0].islower():
                    continue

                # 宏常量应该全大写
                if not const_name.isupper() and not const_name.startswith('k'):
                    # 检查是否是混合大小写
                    if any(c.islower() for c in const_name) and any(c.isupper() for c in const_name):
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=match.start(1) + 1,
                            message=f"宏常量 '{const_name}' 应使用全大写加下划线命名（如 MAX_COUNT）或 k 前缀命名（如 kMaxCount）"
                        ))

        return violations
