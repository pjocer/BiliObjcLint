"""
Forbidden API Rule - 禁用 API 检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation, Severity, ViolationType


# SubType 定义（使用 API 名称作为 sub_type id）
class SubType:
    """forbidden_api 规则的子类型"""
    # C 不安全字符串操作 (ERROR)
    STRCPY = ViolationType("strcpy", "strcpy 不安全，请使用 strlcpy 或 strncpy", Severity.ERROR)
    STRCAT = ViolationType("strcat", "strcat 不安全，请使用 strlcat 或 strncat", Severity.ERROR)
    SPRINTF = ViolationType("sprintf", "sprintf 不安全，请使用 snprintf", Severity.ERROR)
    GETS = ViolationType("gets", "gets 已废弃且不安全，请使用 fgets", Severity.ERROR)
    VSPRINTF = ViolationType("vsprintf", "vsprintf 不安全，请使用 vsnprintf", Severity.ERROR)
    # C 其他不安全 API (WARNING)
    SCANF = ViolationType("scanf", "scanf 存在缓冲区溢出风险，请使用 fgets + sscanf")
    SYSTEM = ViolationType("system", "system 存在命令注入风险")
    POPEN = ViolationType("popen", "popen 存在命令注入风险")
    STRTOK = ViolationType("strtok", "strtok 非线程安全，请使用 strtok_r")
    # Objective-C 不安全 API (WARNING)
    PERFORM_SELECTOR = ViolationType("perform_selector", "performSelector 可能导致内存泄漏，建议使用 block")
    NS_INVOCATION = ViolationType("ns_invocation", "NSInvocation 类型不安全，建议使用 block")
    OBJC_MSG_SEND = ViolationType("objc_msg_send", "直接调用 objc_msgSend 类型不安全")
    VALUE_FOR_KEY = ViolationType("value_for_key", "KVC valueForKey 可能返回 nil，建议做空值检查")
    # 日志（默认关闭）
    NSLOG = ViolationType("nslog", "请使用统一的日志组件替代 NSLog")
    PRINTF = ViolationType("printf", "请使用统一的日志组件替代 printf")
    # 自定义 API
    CUSTOM = ViolationType("custom", "{message}")


# API 名称到 SubType 的映射
_API_SUBTYPE_MAP = {
    "strcpy": SubType.STRCPY,
    "strcat": SubType.STRCAT,
    "sprintf": SubType.SPRINTF,
    "gets": SubType.GETS,
    "vsprintf": SubType.VSPRINTF,
    "scanf": SubType.SCANF,
    "system": SubType.SYSTEM,
    "popen": SubType.POPEN,
    "strtok": SubType.STRTOK,
    "performSelector": SubType.PERFORM_SELECTOR,
    "NSInvocation": SubType.NS_INVOCATION,
    "objc_msgSend": SubType.OBJC_MSG_SEND,
    "valueForKey": SubType.VALUE_FOR_KEY,
    "NSLog": SubType.NSLOG,
    "printf": SubType.PRINTF,
}


class ForbiddenApiRule(BaseRule):
    """禁用 API 检查"""

    identifier = "forbidden_api"
    name = "Forbidden API Check"
    description = "检测禁止使用的 API"
    display_name = "禁用 API"
    default_severity = "warning"

    # 默认禁用的 API 及替代方案
    # sub_type: 对应的 SubType 名称
    DEFAULT_FORBIDDEN_APIS = [
        # 日志相关（默认关闭）
        {
            "pattern": r"\bNSLog\s*\(",
            "sub_type": "NSLog",
            "enabled": False
        },
        {
            "pattern": r"\bprintf\s*\(",
            "sub_type": "printf",
            "enabled": False
        },

        # C 不安全字符串操作（严重，error 级别）
        {
            "pattern": r"\bstrcpy\s*\(",
            "sub_type": "strcpy",
            "enabled": True
        },
        {
            "pattern": r"\bstrcat\s*\(",
            "sub_type": "strcat",
            "enabled": True
        },
        {
            "pattern": r"\bsprintf\s*\(",
            "sub_type": "sprintf",
            "enabled": True
        },
        {
            "pattern": r"\bgets\s*\(",
            "sub_type": "gets",
            "enabled": True
        },
        {
            "pattern": r"\bvsprintf\s*\(",
            "sub_type": "vsprintf",
            "enabled": True
        },

        # C 其他不安全 API（warning 级别）
        {
            "pattern": r"\bscanf\s*\(",
            "sub_type": "scanf",
            "enabled": True
        },
        {
            "pattern": r"\bsystem\s*\(",
            "sub_type": "system",
            "enabled": True
        },
        {
            "pattern": r"\bpopen\s*\(",
            "sub_type": "popen",
            "enabled": True
        },
        {
            "pattern": r"\bstrtok\s*\(",
            "sub_type": "strtok",
            "enabled": True
        },

        # Objective-C 不安全 API（warning 级别）
        {
            "pattern": r"\bperformSelector\s*:",
            "sub_type": "performSelector",
            "enabled": True
        },
        {
            "pattern": r"\bNSInvocation\b",
            "sub_type": "NSInvocation",
            "enabled": True
        },
        {
            "pattern": r"\bobjc_msgSend\s*\(",
            "sub_type": "objc_msgSend",
            "enabled": True
        },
        {
            "pattern": r"\bvalueForKey\s*:",
            "sub_type": "valueForKey",
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
                # 自定义 API 使用 CUSTOM SubType
                api["sub_type"] = None  # 标记为自定义
                apis_to_check.append(api)
            elif isinstance(api, str):
                # 简单字符串格式
                apis_to_check.append({
                    "pattern": re.escape(api),
                    "message": f"禁止使用 {api}",
                    "sub_type": None  # 标记为自定义
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
                sub_type_name = api.get("sub_type")

                if pattern and re.search(pattern, line):
                    # 获取对应的 ViolationType
                    if sub_type_name and sub_type_name in _API_SUBTYPE_MAP:
                        violation_type = _API_SUBTYPE_MAP[sub_type_name]
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=1,
                            lines=lines,
                            violation_type=violation_type,
                            related_lines=related_lines
                        ))
                    else:
                        # 自定义 API 使用 CUSTOM SubType
                        message = api.get("message", "禁止使用此 API")
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=1,
                            lines=lines,
                            violation_type=SubType.CUSTOM,
                            related_lines=related_lines,
                            message_vars={"message": message}
                        ))

        return violations
