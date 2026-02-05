"""
Weak Delegate Rule - delegate 应使用 weak 属性
"""
import re
from typing import List, Set, Tuple

from ..base_rule import BaseRule
from ..rule_utils import find_statement_end, get_property_range
from core.lint.reporter import Violation, Severity


class WeakDelegateRule(BaseRule):
    """delegate 应使用 weak 属性"""

    identifier = "weak_delegate"
    name = "Weak Delegate Check"
    description = "检查 delegate 属性是否使用 weak 修饰"
    default_severity = "error"

    # @property 开始模式
    PROPERTY_START_PATTERN = re.compile(r'@property\s*\(')
    # delegate 属性名模式（在完整声明中匹配）
    DELEGATE_NAME_PATTERN = re.compile(r'\b(\w*[dD]elegate)\s*;')

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        line_num = 1
        while line_num <= len(lines):
            line = lines[line_num - 1]

            # 检测 @property 开始
            if self.PROPERTY_START_PATTERN.search(line):
                property_start = line_num
                # 通过 get_related_lines 获取属性声明范围
                related_lines = self.get_related_lines(file_path, property_start, lines)
                property_end = related_lines[1]

                # 合并多行属性声明
                full_declaration = ' '.join(
                    lines[i].strip() for i in range(property_start - 1, property_end)
                )

                # 检查是否是 delegate 属性
                name_match = self.DELEGATE_NAME_PATTERN.search(full_declaration)
                if name_match:
                    prop_name = name_match.group(1)

                    # 提取修饰符
                    modifier_match = re.search(r'@property\s*\(([^)]*)\)', full_declaration)
                    if modifier_match:
                        modifiers = modifier_match.group(1).lower()

                        # 检查修饰符
                        violation = self._check_modifiers(
                            file_path, property_start, prop_name, modifiers, lines, related_lines
                        )
                        if violation:
                            violations.append(violation)

                line_num = property_end + 1
            else:
                line_num += 1

        return violations

    def _check_modifiers(self, file_path: str, line: int, prop_name: str,
                         modifiers: str, lines: List[str], related_lines: Tuple[int, int]) -> Violation:
        """检查属性修饰符"""
        # weak 是正确的
        if 'weak' in modifiers:
            return None

        # unsafe_unretained - 警告，建议改用 weak
        if 'unsafe_unretained' in modifiers:
            return self.create_violation_with_severity(
                file_path=file_path,
                line=line,
                column=1,
                message=f"'{prop_name}' 使用 unsafe_unretained，建议改为 weak 以避免野指针",
                severity=Severity.WARNING,
                lines=lines,
                related_lines=related_lines
            )

        # strong/retain/copy - 错误，可能导致循环引用
        if any(m in modifiers for m in ['strong', 'retain', 'copy']):
            return self.create_violation(
                file_path=file_path,
                line=line,
                column=1,
                message=f"'{prop_name}' 应使用 weak 修饰以避免循环引用",
                lines=lines,
                related_lines=related_lines
            )

        # assign 是可以接受的（传统方式）
        if 'assign' in modifiers:
            return None

        # 其他情况（没有指定内存语义）- 建议使用 weak
        return self.create_violation(
            file_path=file_path,
            line=line,
            column=1,
            message=f"'{prop_name}' 建议使用 weak 修饰",
            lines=lines,
            related_lines=related_lines
        )

    def get_related_lines(self, file_path: str, line: int, lines: List[str]) -> Tuple[int, int]:
        """
        获取属性声明范围

        从 @property 到 ;
        """
        return get_property_range(lines, line)
