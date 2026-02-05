"""
Enum Naming Rule - 枚举命名检查
"""
import re
from typing import List, Set, Tuple

from ..base_rule import BaseRule
from ..rule_utils import find_statement_end
from core.lint.reporter import Violation


class EnumNamingRule(BaseRule):
    """枚举命名检查"""

    identifier = "enum_naming"
    name = "Enum Naming Check"
    description = "检查枚举命名是否使用指定前缀"
    default_severity = "warning"

    # typedef NS_ENUM(NSInteger, XXXType) { ... };
    # typedef NS_OPTIONS(NSUInteger, XXXOptions) { ... };
    ENUM_PATTERN = re.compile(
        r'typedef\s+NS_(?:ENUM|OPTIONS)\s*\([^,]+,\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)'
    )

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 获取配置的前缀列表
        prefixes = self.get_param("prefixes", [])

        line_num = 1
        while line_num <= len(lines):
            line = lines[line_num - 1]

            # 跳过注释行
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                line_num += 1
                continue

            # 检测枚举声明
            match = self.ENUM_PATTERN.search(line)
            if match:
                enum_name = match.group(1)
                enum_start = line_num
                # 通过 get_related_lines 获取枚举声明范围
                related_lines = self.get_related_lines(file_path, enum_start, lines)
                enum_end = related_lines[1]

                # 检查前缀
                if prefixes:
                    has_valid_prefix = any(enum_name.startswith(prefix) for prefix in prefixes)
                    if not has_valid_prefix:
                        prefixes_str = ', '.join(prefixes)
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=match.start(1) + 1,
                            message=f"枚举 '{enum_name}' 应使用指定前缀（{prefixes_str}）",
                            related_lines=related_lines
                        ))

                line_num = enum_end + 1
            else:
                line_num += 1

        return violations

    def get_related_lines(self, file_path: str, line: int, lines: List[str]) -> Tuple[int, int]:
        """
        获取枚举声明范围

        从 typedef 到 ;
        """
        start = line
        end = find_statement_end(lines, start, ';')
        return (start, end)
