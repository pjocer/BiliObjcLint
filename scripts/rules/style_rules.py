"""
Style Rules - 代码风格规则
"""
import re
from typing import List, Set

from .base_rule import BaseRule
from core.reporter import Violation


class LineLengthRule(BaseRule):
    """行长度检查"""

    identifier = "line_length"
    name = "Line Length Check"
    description = "检查代码行是否超过最大长度"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        max_length = self.get_param("max_length", 120)

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 忽略 URL 和 import 语句
            if 'http://' in line or 'https://' in line:
                continue
            if line.strip().startswith('#import') or line.strip().startswith('@import'):
                continue

            line_length = len(line)
            if line_length > max_length:
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=max_length + 1,
                    message=f"行长度 {line_length} 超过限制 {max_length}"
                ))

        return violations


class MethodLengthRule(BaseRule):
    """方法长度检查"""

    identifier = "method_length"
    name = "Method Length Check"
    description = "检查方法是否超过最大行数"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        max_lines = self.get_param("max_lines", 80)

        # 简单的方法检测：匹配方法开始和结束
        method_start_pattern = r'^[-+]\s*\([^)]+\)'
        brace_count = 0
        in_method = False
        method_start_line = 0
        method_name = ""

        for line_num, line in enumerate(lines, 1):
            # 检测方法开始
            if re.match(method_start_pattern, line.strip()):
                in_method = True
                method_start_line = line_num
                brace_count = 0

                # 提取方法名
                match = re.search(r'^[-+]\s*\([^)]+\)\s*([a-zA-Z_][a-zA-Z0-9_:]*)', line.strip())
                if match:
                    method_name = match.group(1)

            if in_method:
                brace_count += line.count('{') - line.count('}')

                # 方法结束
                if brace_count <= 0 and '{' in content[sum(len(l)+1 for l in lines[:method_start_line]):]:
                    method_length = line_num - method_start_line + 1

                    if method_length > max_lines:
                        # 检查方法起始行是否在变更范围内
                        if not changed_lines or method_start_line in changed_lines or any(
                            l in changed_lines for l in range(method_start_line, line_num + 1)
                        ):
                            violations.append(self.create_violation(
                                file_path=file_path,
                                line=method_start_line,
                                column=1,
                                message=f"方法 '{method_name}' 共 {method_length} 行，超过限制 {max_lines} 行"
                            ))

                    in_method = False

        return violations


class TodoFixmeRule(BaseRule):
    """TODO/FIXME 检查"""

    identifier = "todo_fixme"
    name = "TODO/FIXME Check"
    description = "检测代码中的 TODO 和 FIXME 注释"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 匹配 TODO、FIXME、HACK、XXX 等标记
        pattern = r'(?://|/\*|\*)\s*(TODO|FIXME|HACK|XXX|BUG)[\s:]*(.{0,50})'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                tag = match.group(1).upper()
                desc = match.group(2).strip() if match.group(2) else ""

                message = f"发现 {tag} 标记"
                if desc:
                    message += f": {desc}"

                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=match.start() + 1,
                    message=message
                ))

        return violations


class FileHeaderRule(BaseRule):
    """文件头注释检查"""

    identifier = "file_header"
    name = "File Header Check"
    description = "检查文件是否包含必要的头注释"
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
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=1,
                    column=1,
                    message=f"文件头注释缺少必要信息: {keyword}"
                ))
                break  # 只报告一次

        return violations
