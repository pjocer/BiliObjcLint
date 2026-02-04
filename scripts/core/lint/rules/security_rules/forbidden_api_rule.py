"""
Forbidden API Rule - 禁用 API 检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation


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
