"""
Rule Utilities - 规则公共工具模块

抽取所有规则共享的工具方法，减少代码重复。
"""
import re
from typing import List, Tuple, Optional


# 安全值模式常量（一定非 nil 的值）
SAFE_VALUE_PATTERNS = [
    re.compile(r'^@".*"$'),           # 字符串字面量
    re.compile(r'^@\d+\.?\d*$'),      # 数字字面量 @123, @3.14
    re.compile(r'^@\(.+\)$'),         # 装箱表达式 @(expr)
    re.compile(r'^@(YES|NO|TRUE|FALSE|true|false)$'),  # 布尔字面量
    re.compile(r'^@\{.*\}$'),         # 嵌套字典
    re.compile(r'^@\[.*\]$'),         # 嵌套数组
    re.compile(r'^nil$'),             # nil 本身（显式使用）
]


def strip_line_comment(line: str) -> str:
    """
    移除行尾注释 //

    Args:
        line: 源代码行

    Returns:
        移除注释后的代码
    """
    # 需要处理字符串中的 // 不被误判
    in_string = False
    escape_next = False

    for i, char in enumerate(line):
        if escape_next:
            escape_next = False
            continue

        if char == '\\':
            escape_next = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if not in_string and i < len(line) - 1 and line[i:i+2] == '//':
            return line[:i]

    return line


def is_comment_line(line: str) -> bool:
    """
    判断是否是注释行

    Args:
        line: 源代码行

    Returns:
        True 如果是注释行
    """
    stripped = line.strip()
    return (stripped.startswith('//') or
            stripped.startswith('/*') or
            stripped.startswith('*'))


def strip_block_comments(content: str) -> str:
    """
    处理多行块注释 /* ... */

    Args:
        content: 源代码内容

    Returns:
        移除块注释后的内容
    """
    result = []
    i = 0
    in_string = False
    escape_next = False

    while i < len(content):
        if escape_next:
            result.append(content[i])
            escape_next = False
            i += 1
            continue

        if content[i] == '\\':
            escape_next = True
            result.append(content[i])
            i += 1
            continue

        if content[i] == '"' and not in_string:
            in_string = True
            result.append(content[i])
            i += 1
            continue

        if content[i] == '"' and in_string:
            in_string = False
            result.append(content[i])
            i += 1
            continue

        if in_string:
            result.append(content[i])
            i += 1
            continue

        # 检测块注释开始
        if i < len(content) - 1 and content[i:i+2] == '/*':
            # 查找块注释结束
            end = content.find('*/', i + 2)
            if end != -1:
                # 用空格替换注释内容（保持行号）
                comment = content[i:end+2]
                result.append(' ' * comment.count('\n'))
                i = end + 2
                continue
            else:
                # 未闭合的块注释，跳到末尾
                break

        result.append(content[i])
        i += 1

    return ''.join(result)


def is_safe_value(value: str, patterns: Optional[List[re.Pattern]] = None) -> bool:
    """
    检查值是否安全（一定非 nil）

    Args:
        value: 要检查的值
        patterns: 可选的安全模式列表，默认使用 SAFE_VALUE_PATTERNS

    Returns:
        True 如果值是安全的
    """
    value = value.strip()

    if not value:
        return True

    check_patterns = patterns or SAFE_VALUE_PATTERNS

    for pattern in check_patterns:
        if pattern.match(value):
            return True

    return False


def find_matching_brace(lines: List[str], start_line: int,
                        open_char: str = '{', close_char: str = '}') -> int:
    """
    从指定行开始，查找匹配的闭合括号所在行

    使用括号配对算法，正确处理嵌套结构。

    Args:
        lines: 文件所有行
        start_line: 开始搜索的行号（1-indexed）
        open_char: 开括号字符，如 '{', '[', '('
        close_char: 闭括号字符，如 '}', ']', ')'

    Returns:
        闭合括号所在行号（1-indexed），找不到返回文件末尾

    Example:
        ```objc
        - (void)method1 {      // line 10, brace_count = 1
            if (x) {           // line 11, brace_count = 2
            }                  // line 12, brace_count = 1
            for (...) {        // line 13, brace_count = 2
            }                  // line 14, brace_count = 1
        }                      // line 15, brace_count = 0 → 方法结束
        ```
        find_matching_brace(lines, 10, '{', '}') → 15
    """
    brace_count = 0
    found_first = False

    for i in range(start_line - 1, len(lines)):
        line = lines[i]

        # 跳过字符串中的括号
        in_string = False
        escape_next = False

        for char in line:
            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == open_char:
                brace_count += 1
                found_first = True
            elif char == close_char:
                brace_count -= 1
                if found_first and brace_count == 0:
                    return i + 1  # 1-indexed

    return len(lines)


def find_statement_end(lines: List[str], start_line: int, end_char: str = ';') -> int:
    """
    从指定行开始，查找语句结束符所在行

    用于处理多行声明（如 @property、方法声明等）。
    跳过字符串和注释中的字符。

    Args:
        lines: 文件所有行
        start_line: 开始搜索的行号（1-indexed）
        end_char: 语句结束符，如 ';', '>'

    Returns:
        结束符所在行号（1-indexed），找不到返回起始行
    """
    for i in range(start_line - 1, min(len(lines), start_line + 20)):
        line = lines[i]

        # 跳过字符串和注释中的字符
        in_string = False
        escape_next = False
        j = 0

        while j < len(line):
            char = line[j]

            if escape_next:
                escape_next = False
                j += 1
                continue

            if char == '\\':
                escape_next = True
                j += 1
                continue

            if char == '"':
                in_string = not in_string
                j += 1
                continue

            if in_string:
                j += 1
                continue

            # 跳过单行注释 //
            if j < len(line) - 1 and line[j:j+2] == '//':
                break  # 跳过当前行剩余部分

            if char == end_char:
                return i + 1  # 1-indexed

            j += 1

    return start_line


def get_method_range(lines: List[str], method_start_line: int) -> Tuple[int, int]:
    """
    获取方法的完整范围（从方法声明行到闭合大括号）

    Args:
        lines: 文件所有行
        method_start_line: 方法声明行号（1-indexed）

    Returns:
        (start_line, end_line): 方法范围，1-indexed, inclusive
    """
    method_end = find_matching_brace(lines, method_start_line, '{', '}')
    return (method_start_line, method_end)


def get_property_range(lines: List[str], property_start_line: int) -> Tuple[int, int]:
    """
    获取 @property 声明的完整范围（从 @property 到 ;）

    Args:
        lines: 文件所有行
        property_start_line: @property 所在行号（1-indexed）

    Returns:
        (start_line, end_line): 属性声明范围，1-indexed, inclusive
    """
    property_end = find_statement_end(lines, property_start_line, ';')
    return (property_start_line, property_end)
