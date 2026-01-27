"""
Security Rules - 安全相关规则
"""
import re
from typing import List, Set

from .base_rule import BaseRule
from core.reporter import Violation


class ForbiddenApiRule(BaseRule):
    """禁用 API 检查"""

    identifier = "forbidden_api"
    name = "Forbidden API Check"
    description = "检测禁止使用的 API"
    default_severity = "error"

    # 默认禁用的 API 及替代方案
    DEFAULT_FORBIDDEN_APIS = [
        {
            "pattern": r"\bNSLog\s*\(",
            "message": "请使用统一的日志组件替代 NSLog",
            "enabled": False  # 默认关闭，需要配置启用
        },
        {
            "pattern": r"\bprintf\s*\(",
            "message": "请使用统一的日志组件替代 printf",
            "enabled": False
        },
        {
            "pattern": r"\bstrcpy\s*\(",
            "message": "strcpy 不安全，请使用 strlcpy 或 strncpy",
            "enabled": True
        },
        {
            "pattern": r"\bstrcat\s*\(",
            "message": "strcat 不安全，请使用 strlcat 或 strncat",
            "enabled": True
        },
        {
            "pattern": r"\bsprintf\s*\(",
            "message": "sprintf 不安全，请使用 snprintf",
            "enabled": True
        },
        {
            "pattern": r"\bgets\s*\(",
            "message": "gets 已废弃且不安全，请使用 fgets",
            "enabled": True
        },
    ]

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 合并默认和自定义的禁用 API
        apis_to_check = []

        # 添加默认的（如果启用）
        for api in self.DEFAULT_FORBIDDEN_APIS:
            if api.get("enabled", True):
                apis_to_check.append(api)

        # 添加自定义的
        custom_apis = self.get_param("apis", [])
        for api in custom_apis:
            if isinstance(api, dict):
                apis_to_check.append(api)
            elif isinstance(api, str):
                # 简单字符串格式
                apis_to_check.append({
                    "pattern": re.escape(api),
                    "message": f"禁止使用 {api}"
                })

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 跳过注释行
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            for api in apis_to_check:
                pattern = api.get("pattern", "")
                message = api.get("message", "禁止使用此 API")

                if pattern and re.search(pattern, line):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=1,
                        message=message
                    ))

        return violations


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
    ]

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 跳过注释
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            for pattern, message in self.SENSITIVE_PATTERNS:
                if re.search(pattern, line):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=1,
                        message=message
                    ))
                    break  # 每行只报告一次

        return violations


class InsecureRandomRule(BaseRule):
    """不安全随机数检查"""

    identifier = "insecure_random"
    name = "Insecure Random Check"
    description = "检测不安全的随机数生成方式"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 不安全的随机数 API
        insecure_patterns = [
            (r'\brand\s*\(\s*\)', "rand() 不安全，请使用 arc4random()"),
            (r'\brandom\s*\(\s*\)', "random() 不安全，请使用 arc4random()"),
            (r'\bdrand48\s*\(\s*\)', "drand48() 不安全，请使用 arc4random()"),
        ]

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            for pattern, message in insecure_patterns:
                if re.search(pattern, line):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=1,
                        message=message
                    ))

        return violations
