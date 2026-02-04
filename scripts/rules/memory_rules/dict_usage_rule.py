"""
Dict Usage Rule - 字典方法使用检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation


class DictUsageRule(BaseRule):
    """字典方法使用检查

    检测 -[NSMutableDictionary setObject:forKey:] 的使用，
    建议使用 setValue:forKey: 替代以避免 nil 崩溃。
    """

    identifier = "dict_usage"
    name = "Dictionary Usage Check"
    description = "检查 NSMutableDictionary 的 setObject:forKey: 使用"
    default_severity = "warning"

    # 匹配 setObject:forKey: 方法调用
    # 例如: [dict setObject:value forKey:key]
    #       [self.dict setObject:value forKey:key]
    # 注意：value 可能包含空格（如 @"some value"），所以用 .+? 而非 \S+
    SET_OBJECT_PATTERN = re.compile(
        r'\[\s*\S+\s+setObject\s*:.+?\s+forKey\s*:'
    )

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        del content  # unused
        violations = []

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 跳过注释行
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            # 移除行尾注释
            comment_pos = line.find('//')
            check_line = line[:comment_pos] if comment_pos != -1 else line

            # 检测 setObject:forKey: 使用
            match = self.SET_OBJECT_PATTERN.search(check_line)
            if match:
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=match.start() + 1,
                    message="请确认 object 非空，建议使用 `setValue:forKey:` 替代"
                ))

        return violations
