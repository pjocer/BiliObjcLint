"""
Property Naming Rule - 属性命名检查（小驼峰）
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation


class PropertyNamingRule(BaseRule):
    """属性命名检查（小驼峰）"""

    identifier = "property_naming"
    name = "Property Naming Check"
    description = "检查属性命名是否符合小驼峰规范"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 匹配 @property 声明
        # @property (nonatomic, strong) NSString *userName;
        pattern = r'@property\s*\([^)]*\)\s*\w+[\s*]+\*?\s*(\w+)\s*;'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            match = re.search(pattern, line)
            if match:
                prop_name = match.group(1)

                # 检查是否以小写字母开头
                if prop_name and prop_name[0].isupper():
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=match.start(1) + 1,
                        message=f"属性名 '{prop_name}' 应使用小驼峰命名（首字母小写）"
                    ))

                # 检查是否包含下划线（IBOutlet 除外）
                if '_' in prop_name and 'IBOutlet' not in line:
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=match.start(1) + 1,
                        message=f"属性名 '{prop_name}' 不应包含下划线，请使用小驼峰命名"
                    ))

        return violations
