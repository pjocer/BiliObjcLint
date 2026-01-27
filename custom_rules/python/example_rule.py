"""
示例自定义规则

这个文件展示如何编写自定义 Python 规则。
将你的自定义规则文件放在 custom_rules/python/ 目录下，
它们会被自动加载。

使用步骤:
1. 继承 BaseRule 基类
2. 定义 identifier、name、description、default_severity
3. 实现 check 方法
"""
import re
from typing import List, Set

# 导入基类
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from rules.base_rule import BaseRule
from core.reporter import Violation


class NoMagicNumberRule(BaseRule):
    """
    魔法数字检查

    检测代码中的硬编码数字（魔法数字），
    建议使用常量替代。
    """

    identifier = "no_magic_number"
    name = "No Magic Number"
    description = "禁止使用魔法数字，请使用命名常量"
    default_severity = "warning"

    # 允许的数字（不视为魔法数字）
    ALLOWED_NUMBERS = {
        '0', '1', '-1', '2', '0.0', '1.0', '0.5',
        '100', '1000',  # 常见百分比计算
    }

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 匹配数字（整数和浮点数）
        number_pattern = r'(?<![a-zA-Z_])(-?\d+\.?\d*)(?![a-zA-Z_\d])'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 跳过注释、#define、enum、const 声明
            stripped = line.strip()
            if (stripped.startswith('//') or
                stripped.startswith('/*') or
                stripped.startswith('*') or
                stripped.startswith('#define') or
                'enum' in line or
                'const ' in line):
                continue

            # 跳过数组索引中的简单数字
            if re.search(r'\[\s*\d+\s*\]', line):
                continue

            for match in re.finditer(number_pattern, line):
                number = match.group(1)

                # 跳过允许的数字
                if number in self.ALLOWED_NUMBERS:
                    continue

                # 跳过字符串中的数字
                before = line[:match.start()]
                if before.count('"') % 2 == 1 or before.count("'") % 2 == 1:
                    continue

                # 跳过方法参数默认值位置的数字
                if ':' in line and match.start() > line.index(':'):
                    continue

                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=match.start() + 1,
                    message=f"魔法数字 '{number}'，建议使用命名常量"
                ))

        return violations


class NoChineseInCodeRule(BaseRule):
    """
    代码中禁止中文检查

    检测代码（非字符串/注释）中的中文字符
    """

    identifier = "no_chinese_in_code"
    name = "No Chinese in Code"
    description = "代码中不应包含中文（字符串和注释除外）"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        chinese_pattern = r'[\u4e00-\u9fff]'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 移除字符串内容
            code_line = re.sub(r'@?"[^"]*"', '""', line)
            code_line = re.sub(r"'[^']*'", "''", code_line)

            # 移除注释
            code_line = re.sub(r'//.*$', '', code_line)
            code_line = re.sub(r'/\*.*?\*/', '', code_line)

            # 检查剩余代码中的中文
            if re.search(chinese_pattern, code_line):
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=1,
                    message="代码中包含中文字符"
                ))

        return violations


# 更多自定义规则示例...
# class YourCustomRule(BaseRule):
#     identifier = "your_rule_id"
#     name = "Your Rule Name"
#     description = "Your rule description"
#     default_severity = "warning"
#
#     def check(self, file_path, content, lines, changed_lines):
#         violations = []
#         # 实现你的检查逻辑
#         return violations
