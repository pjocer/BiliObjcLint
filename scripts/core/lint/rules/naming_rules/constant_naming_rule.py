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

    # #define 宏常量模式
    DEFINE_PATTERN = re.compile(r'#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+')

    # const/static 常量模式
    # static const NSString *kXXX = ...
    # static NSString *const kXXX = ...
    # const NSInteger kXXX = ...
    CONST_PATTERN = re.compile(
        r'(?:static\s+)?(?:const\s+)?(?:NS\w+|CGFloat|NSInteger|NSUInteger|BOOL|int|float|double|char)\s*'
        r'\*?\s*(?:const\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*='
    )

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 跳过注释行
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            # 获取 related_lines（单行）
            related_lines = self.get_related_lines(file_path, line_num, lines)

            # 1. 检查 #define 宏常量
            define_match = self.DEFINE_PATTERN.search(line)
            if define_match:
                violation = self._check_define_naming(line, line_num, define_match, file_path, lines, related_lines)
                if violation:
                    violations.append(violation)
                continue

            # 2. 检查 const/static 常量
            const_match = self.CONST_PATTERN.search(line)
            if const_match:
                violation = self._check_const_naming(line, line_num, const_match, file_path, lines, related_lines)
                if violation:
                    violations.append(violation)

        return violations

    def _check_define_naming(self, line: str, line_num: int, match, file_path: str, lines: List[str], related_lines):
        """检查 #define 宏常量命名"""
        const_name = match.group(1)

        # 跳过函数宏（后面紧跟括号）
        after_name = line[match.end() - 1:]
        if after_name.startswith('('):
            return None

        # 跳过小写字母开头的宏（通常是函数式宏或特殊用途）
        if const_name[0].islower():
            return None

        # 宏常量应该全大写或 k 前缀
        if not const_name.isupper() and not const_name.startswith('k'):
            # 检查是否是混合大小写
            if any(c.islower() for c in const_name) and any(c.isupper() for c in const_name):
                return self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=match.start(1) + 1,
                    message=f"宏常量 '{const_name}' 应使用全大写加下划线命名（如 MAX_COUNT）或 k 前缀命名（如 kMaxCount）",
                    lines=lines,
                    related_lines=related_lines
                )
        return None

    def _check_const_naming(self, line: str, line_num: int, match, file_path: str, lines: List[str], related_lines):
        """检查 const/static 常量命名"""
        const_name = match.group(1)

        # 跳过明显的局部变量（小写字母开头且不含 static/const 关键字）
        if const_name[0].islower() and 'static' not in line and 'const' not in line:
            return None

        # 如果包含 static 或 const，应该使用 k 前缀或全大写命名
        if 'static' in line or 'const' in line:
            # k 前缀是正确的
            if const_name.startswith('k') and len(const_name) > 1 and const_name[1].isupper():
                return None

            # 全大写是正确的
            if const_name.isupper():
                return None

            # 其他情况需要警告
            if const_name[0].islower() or (not const_name.startswith('k') and not const_name.isupper()):
                return self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=match.start(1) + 1,
                    message=f"常量 '{const_name}' 应使用 k 前缀驼峰命名（如 kMaxCount）或全大写下划线命名（如 MAX_COUNT）",
                    lines=lines,
                    related_lines=related_lines
                )

        return None
