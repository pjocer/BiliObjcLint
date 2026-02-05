"""
File Header Rule - 文件头注释检查
"""
from typing import List, Set, Tuple

from ..base_rule import BaseRule
from core.lint.reporter import Violation, ViolationType


# SubType 定义
class SubType:
    """file_header 规则的子类型"""
    MISSING_KEYWORD = ViolationType("missing_keyword", "文件头注释缺少必要信息: {keyword}")


class FileHeaderRule(BaseRule):
    """文件头注释检查"""

    identifier = "file_header"
    name = "File Header Check"
    description = "检查文件是否包含必要的头注释"
    display_name = "文件头注释"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 如果是增量检查且第一行不在变更范围，跳过
        if changed_lines and 1 not in changed_lines:
            return violations

        required_keywords = self.get_param("required_keywords", [])
        if not required_keywords:
            return violations

        # 检查前 20 行是否有必要的关键字
        header_lines = '\n'.join(lines[:20])

        for keyword in required_keywords:
            if keyword not in header_lines:
                related_lines = self.get_related_lines(file_path, 1, lines)
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=1,
                    column=1,
                    lines=lines,
                    violation_type=SubType.MISSING_KEYWORD,
                    related_lines=related_lines,
                    message_vars={"keyword": keyword}
                ))
                break  # 只报告一次

        return violations

    def get_related_lines(self, file_path: str, line: int, lines: List[str]) -> Tuple[int, int]:
        """
        获取文件头范围

        文件头检查范围为前 20 行
        """
        return (1, min(20, len(lines)))
