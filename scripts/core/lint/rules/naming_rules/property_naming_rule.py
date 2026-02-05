"""
Property Naming Rule - 属性命名检查（小驼峰）
"""
import re
from typing import List, Set, Tuple

from ..base_rule import BaseRule
from ..rule_utils import find_statement_end, get_property_range
from core.lint.reporter import Violation, ViolationType


# SubType 定义
class SubType:
    """property_naming 规则的子类型"""
    UPPERCASE_START = ViolationType(
        "uppercase_start",
        "属性名 '{prop}' 应使用小驼峰命名（首字母小写）"
    )
    CONTAINS_UNDERSCORE = ViolationType(
        "contains_underscore",
        "属性名 '{prop}' 不应包含下划线，请使用小驼峰命名"
    )


class PropertyNamingRule(BaseRule):
    """属性命名检查（小驼峰）"""

    identifier = "property_naming"
    name = "Property Naming Check"
    description = "检查属性命名是否符合小驼峰规范"
    display_name = "属性命名"
    default_severity = "warning"

    # @property 开始模式
    PROPERTY_START_PATTERN = re.compile(r'@property\s*\(')
    # 属性名提取模式（在完整声明中匹配）
    PROPERTY_NAME_PATTERN = re.compile(r'\*?\s*(\w+)\s*;')

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

                # 检查是否是 IBOutlet（跳过下划线检查）
                is_iboutlet = 'IBOutlet' in full_declaration

                # 提取属性名
                name_match = self.PROPERTY_NAME_PATTERN.search(full_declaration)
                if name_match:
                    prop_name = name_match.group(1)

                    # 检查是否以小写字母开头
                    if prop_name and prop_name[0].isupper():
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=property_start,
                            column=1,
                            lines=lines,
                            violation_type=SubType.UPPERCASE_START,
                            related_lines=related_lines,
                            message_vars={"prop": prop_name}
                        ))

                    # 检查是否包含下划线（IBOutlet 除外）
                    if '_' in prop_name and not is_iboutlet:
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=property_start,
                            column=1,
                            lines=lines,
                            violation_type=SubType.CONTAINS_UNDERSCORE,
                            related_lines=related_lines,
                            message_vars={"prop": prop_name}
                        ))

                line_num = property_end + 1
            else:
                line_num += 1

        return violations

    def get_related_lines(self, file_path: str, line: int, lines: List[str]) -> Tuple[int, int]:
        """
        获取属性声明范围

        从 @property 到 ;
        """
        return get_property_range(lines, line)
