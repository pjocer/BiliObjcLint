"""
Hardcoded Credentials Rule - 硬编码凭证检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation


class HardcodedCredentialsRule(BaseRule):
    """硬编码凭证检查"""

    identifier = "hardcoded_credentials"
    name = "Hardcoded Credentials Check"
    description = "检测硬编码的密码、密钥等敏感信息"
    default_severity = "error"

    # 敏感关键字模式
    SENSITIVE_PATTERNS = [
        # 密码
        (r'(?i)password\s*[:=]\s*@?"[^"]{4,}"', "检测到硬编码密码"),
        (r'(?i)passwd\s*[:=]\s*@?"[^"]{4,}"', "检测到硬编码密码"),
        (r'(?i)pwd\s*[:=]\s*@?"[^"]{4,}"', "检测到硬编码密码"),

        # API Key / Secret
        (r'(?i)api[_-]?key\s*[:=]\s*@?"[^"]{8,}"', "检测到硬编码 API Key"),
        (r'(?i)api[_-]?secret\s*[:=]\s*@?"[^"]{8,}"', "检测到硬编码 API Secret"),
        (r'(?i)app[_-]?secret\s*[:=]\s*@?"[^"]{8,}"', "检测到硬编码 App Secret"),
        (r'(?i)secret[_-]?key\s*[:=]\s*@?"[^"]{8,}"', "检测到硬编码 Secret Key"),

        # Token
        (r'(?i)access[_-]?token\s*[:=]\s*@?"[^"]{8,}"', "检测到硬编码 Access Token"),
        (r'(?i)auth[_-]?token\s*[:=]\s*@?"[^"]{8,}"', "检测到硬编码 Auth Token"),

        # 私钥
        (r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----', "检测到硬编码私钥"),

        # AWS
        (r'AKIA[0-9A-Z]{16}', "检测到 AWS Access Key ID"),
        (r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*@?"[^"]{20,}"', "检测到 AWS Secret Access Key"),
    ]

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 注释中也检测凭证（凭证不应该出现在任何地方，包括注释）

            # 获取 related_lines（单行）
            related_lines = self.get_related_lines(file_path, line_num, lines)

            for pattern, message in self.SENSITIVE_PATTERNS:
                if re.search(pattern, line):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=1,
                        message=message,
                        related_lines=related_lines
                    ))
                    break  # 每行只报告一次

        return violations
