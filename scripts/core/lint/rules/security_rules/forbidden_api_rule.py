"""
Forbidden API Rule - 禁用 API 检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation, Severity


class ForbiddenApiRule(BaseRule):
    """禁用 API 检查"""

    identifier = "forbidden_api"
    name = "Forbidden API Check"
    description = "检测禁止使用的 API"
    default_severity = "warning"

    # 默认禁用的 API 及替代方案
    # severity: error/warning，默认使用规则级别
    DEFAULT_FORBIDDEN_APIS = [
        # 日志相关（默认关闭）
        {
            "pattern": r"\bNSLog\s*\(",
            "message": "请使用统一的日志组件替代 NSLog",
            "enabled": False
        },
        {
            "pattern": r"\bprintf\s*\(",
            "message": "请使用统一的日志组件替代 printf",
            "enabled": False
        },

        # C 不安全字符串操作（严重，error 级别）
        {
            "pattern": r"\bstrcpy\s*\(",
            "message": "strcpy 不安全，请使用 strlcpy 或 strncpy",
            "enabled": True,
            "severity": "error"
        },
        {
            "pattern": r"\bstrcat\s*\(",
            "message": "strcat 不安全，请使用 strlcat 或 strncat",
            "enabled": True,
            "severity": "error"
        },
        {
            "pattern": r"\bsprintf\s*\(",
            "message": "sprintf 不安全，请使用 snprintf",
            "enabled": True,
            "severity": "error"
        },
        {
            "pattern": r"\bgets\s*\(",
            "message": "gets 已废弃且不安全，请使用 fgets",
            "enabled": True,
            "severity": "error"
        },
        {
            "pattern": r"\bvsprintf\s*\(",
            "message": "vsprintf 不安全，请使用 vsnprintf",
            "enabled": True,
            "severity": "error"
        },

        # C 其他不安全 API（warning 级别）
        {
            "pattern": r"\bscanf\s*\(",
            "message": "scanf 存在缓冲区溢出风险，请使用 fgets + sscanf",
            "enabled": True
        },
        {
            "pattern": r"\bsystem\s*\(",
            "message": "system 存在命令注入风险",
            "enabled": True
        },
        {
            "pattern": r"\bpopen\s*\(",
            "message": "popen 存在命令注入风险",
            "enabled": True
        },
        {
            "pattern": r"\bstrtok\s*\(",
            "message": "strtok 非线程安全，请使用 strtok_r",
            "enabled": True
        },

        # Objective-C 不安全 API（warning 级别）
        {
            "pattern": r"\bperformSelector\s*:",
            "message": "performSelector 可能导致内存泄漏，建议使用 block 或直接调用",
            "enabled": True
        },
        {
            "pattern": r"\bNSInvocation\b",
            "message": "NSInvocation 类型不安全，建议使用 block",
            "enabled": True
        },
        {
            "pattern": r"\bobjc_msgSend\s*\(",
            "message": "直接调用 objc_msgSend 类型不安全",
            "enabled": True
        },
        {
            "pattern": r"\bvalueForKey\s*:",
            "message": "KVC valueForKey 可能返回 nil，建议做空值检查",
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

            # 获取 related_lines（单行）
            related_lines = self.get_related_lines(file_path, line_num, lines)

            for api in apis_to_check:
                pattern = api.get("pattern", "")
                message = api.get("message", "禁止使用此 API")
                api_severity = api.get("severity")

                if pattern and re.search(pattern, line):
                    # 如果 API 指定了 severity，使用指定的；否则使用规则默认的
                    if api_severity:
                        try:
                            severity = Severity(api_severity)
                        except ValueError:
                            severity = self.severity
                        violations.append(self.create_violation_with_severity(
                            file_path=file_path,
                            line=line_num,
                            column=1,
                            message=message,
                            severity=severity,
                            related_lines=related_lines
                        ))
                    else:
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=1,
                            message=message,
                            related_lines=related_lines
                        ))

        return violations
