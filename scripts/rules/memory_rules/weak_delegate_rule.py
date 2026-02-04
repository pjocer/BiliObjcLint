"""
Weak Delegate Rule - delegate 应使用 weak 属性
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation


class WeakDelegateRule(BaseRule):
    """delegate 应使用 weak 属性"""

    identifier = "weak_delegate"
    name = "Weak Delegate Check"
    description = "检查 delegate 属性是否使用 weak 修饰"
    default_severity = "error"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 匹配 delegate 属性声明
        # @property (nonatomic, strong) id<XXXDelegate> delegate;
        pattern = r'@property\s*\(([^)]*)\)[^;]*\b(\w*[dD]elegate)\s*;'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            match = re.search(pattern, line)
            if match:
                modifiers = match.group(1).lower()
                prop_name = match.group(2)

                # 检查是否有 weak 修饰符
                if 'weak' not in modifiers:
                    # 检查是否有 strong/retain/copy（不应该用于 delegate）
                    if any(m in modifiers for m in ['strong', 'retain', 'copy']):
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=match.start(2) + 1,
                            message=f"'{prop_name}' 应使用 weak 修饰以避免循环引用"
                        ))
                    elif 'assign' not in modifiers:
                        # 如果既不是 weak 也不是 assign，给出提示
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=match.start(2) + 1,
                            message=f"'{prop_name}' 建议使用 weak 修饰"
                        ))

        return violations
