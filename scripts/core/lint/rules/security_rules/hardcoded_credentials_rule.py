"""
Hardcoded Credentials Rule - 硬编码凭证检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation, Severity, ViolationType


# SubType 定义
class SubType:
    """hardcoded_credentials 规则的子类型"""
    PASSWORD = ViolationType("password", "检测到硬编码密码", Severity.ERROR)
    API_KEY = ViolationType("api_key", "检测到硬编码 API Key", Severity.ERROR)
    API_SECRET = ViolationType("api_secret", "检测到硬编码 API/App Secret", Severity.ERROR)
    TOKEN = ViolationType("token", "检测到硬编码 Token", Severity.ERROR)
    PRIVATE_KEY = ViolationType("private_key", "检测到硬编码私钥", Severity.ERROR)
    AWS_KEY = ViolationType("aws_key", "检测到 AWS Access Key", Severity.ERROR)


class HardcodedCredentialsRule(BaseRule):
    """硬编码凭证检查"""

    identifier = "hardcoded_credentials"
    name = "Hardcoded Credentials Check"
    description = "检测硬编码的密码、密钥等敏感信息"
    display_name = "硬编码凭证"
    default_severity = "error"

    # 敏感关键字模式 (pattern, sub_type)
    SENSITIVE_PATTERNS = [
        # 密码
        (r'(?i)password\s*[:=]\s*@?"[^"]{4,}"', SubType.PASSWORD),
        (r'(?i)passwd\s*[:=]\s*@?"[^"]{4,}"', SubType.PASSWORD),
        (r'(?i)pwd\s*[:=]\s*@?"[^"]{4,}"', SubType.PASSWORD),

        # API Key / Secret
        (r'(?i)api[_-]?key\s*[:=]\s*@?"[^"]{8,}"', SubType.API_KEY),
        (r'(?i)api[_-]?secret\s*[:=]\s*@?"[^"]{8,}"', SubType.API_SECRET),
        (r'(?i)app[_-]?secret\s*[:=]\s*@?"[^"]{8,}"', SubType.API_SECRET),
        (r'(?i)secret[_-]?key\s*[:=]\s*@?"[^"]{8,}"', SubType.API_SECRET),

        # Token
        (r'(?i)access[_-]?token\s*[:=]\s*@?"[^"]{8,}"', SubType.TOKEN),
        (r'(?i)auth[_-]?token\s*[:=]\s*@?"[^"]{8,}"', SubType.TOKEN),

        # 私钥
        (r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----', SubType.PRIVATE_KEY),

        # AWS
        (r'AKIA[0-9A-Z]{16}', SubType.AWS_KEY),
        (r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*@?"[^"]{20,}"', SubType.AWS_KEY),
    ]

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 注释中也检测凭证（凭证不应该出现在任何地方，包括注释）

            # 获取 related_lines（单行）
            related_lines = self.get_related_lines(file_path, line_num, lines)

            for pattern, violation_type in self.SENSITIVE_PATTERNS:
                if re.search(pattern, line):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=1,
                        lines=lines,
                        violation_type=violation_type,
                        related_lines=related_lines
                    ))
                    break  # 每行只报告一次

        return violations
