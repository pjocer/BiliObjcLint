"""
Class Prefix Rule - 类名前缀检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation, ViolationType


# SubType 定义
class SubType:
    """class_prefix 规则的子类型"""
    MISSING_PREFIX = ViolationType(
        "missing_prefix",
        "类名 '{class_name}' 应使用前缀 '{prefix}'"
    )


class ClassPrefixRule(BaseRule):
    """类名前缀检查"""

    identifier = "class_prefix"
    name = "Class Prefix Check"
    description = "检查类名是否使用指定前缀"
    display_name = "类名前缀"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        prefix = self.get_param("prefix", "")
        if not prefix:
            return violations  # 未配置前缀，跳过

        # 匹配 @interface/@implementation 声明
        # @interface ClassName : SuperClass
        # @interface ClassName (Category)
        # @implementation ClassName
        pattern = r'@(?:interface|implementation)\s+([A-Z][A-Za-z0-9_]*)\s*(?:[:(]|$)'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            match = re.search(pattern, line)
            if match:
                class_name = match.group(1)

                # 跳过系统类和常见第三方类前缀
                skip_prefixes = ['NS', 'UI', 'CG', 'CA', 'CF', 'AV', 'MK', 'CL', 'SK', 'SC']
                if any(class_name.startswith(p) for p in skip_prefixes):
                    continue

                # 检查是否使用了指定前缀
                if not class_name.startswith(prefix):
                    related_lines = self.get_related_lines(file_path, line_num, lines)
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=match.start(1) + 1,
                        lines=lines,
                        violation_type=SubType.MISSING_PREFIX,
                        related_lines=related_lines,
                        message_vars={"class_name": class_name, "prefix": prefix}
                    ))

        return violations
