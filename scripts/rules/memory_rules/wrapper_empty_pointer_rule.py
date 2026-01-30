"""
Wrapper Empty Pointer Rule - 容器字面量空指针检查
"""
import re
from typing import List, Set, Optional, Tuple

from ..base_rule import BaseRule
from core.reporter import Violation


class WrapperEmptyPointerRule(BaseRule):
    """容器字面量空指针检查

    检测 @{} 和 @[] 中可能为 nil 的元素，防止运行时崩溃。
    """

    identifier = "wrapper_empty_pointer"
    name = "Wrapper Empty Pointer Check"
    description = "检查容器字面量中的元素是否可能为 nil"
    default_severity = "warning"

    # 安全的值模式（一定非 nil）
    SAFE_VALUE_PATTERNS = [
        re.compile(r'^@".*"$'),           # 字符串字面量
        re.compile(r'^@\d+\.?\d*$'),      # 数字字面量 @123, @3.14
        re.compile(r'^@\(.+\)$'),         # 装箱表达式 @(expr)
        re.compile(r'^@(YES|NO|TRUE|FALSE|true|false)$'),  # 布尔字面量
        re.compile(r'^@\{.*\}$'),         # 嵌套字典
        re.compile(r'^@\[.*\]$'),         # 嵌套数组
        re.compile(r'^nil$'),             # nil 本身（虽然不安全，但这是显式的）
    ]

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 查找所有容器字面量
        containers = self._find_containers(content, lines)

        for container in containers:
            line_num = container['line']

            if not self.should_check_line(line_num, changed_lines):
                continue

            # 跳过注释行
            line = lines[line_num - 1] if line_num <= len(lines) else ''
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            # 检查容器中的每个值
            for value_info in container['values']:
                value = value_info['value']
                col = value_info['column']

                is_safe, unsafe_part = self._is_safe_value(value)
                if not is_safe:
                    # 如果有 unsafe_part（来自三目运算符），使用它作为警告内容
                    warn_value = unsafe_part if unsafe_part else value
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=col,
                        message=f"'{warn_value}' 可能为 nil，请确认其值一定不为空"
                    ))

        return violations

    def _find_containers(self, _content: str, lines: List[str]) -> List[dict]:
        """查找所有容器字面量及其内容（支持多行）"""
        containers = []

        # 追踪多行容器状态
        in_dict = False
        dict_brace_count = 0
        in_array = False
        array_bracket_count = 0

        for line_num, line in enumerate(lines, 1):
            # 跳过注释
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            # 移除行尾注释
            comment_pos = line.find('//')
            check_line = line[:comment_pos] if comment_pos != -1 else line

            # 查找单行字典字面量 @{...}
            dict_containers = self._find_dict_literals(check_line, line_num)
            containers.extend(dict_containers)

            # 查找单行数组字面量 @[...]
            array_containers = self._find_array_literals(check_line, line_num)
            containers.extend(array_containers)

            # 检测多行字典开始 @{ 且未闭合
            if '@{' in check_line:
                # 计算该行的 { 和 } 是否平衡
                after_at_brace = check_line[check_line.find('@{') + 2:]
                open_braces = 1 + after_at_brace.count('{')
                close_braces = after_at_brace.count('}')
                if open_braces > close_braces:
                    in_dict = True
                    dict_brace_count = open_braces - close_braces

            # 如果在多行字典内，检测键值对
            elif in_dict:
                # 检测字典键值对: @"key": value 或带有逗号结尾
                kv_values = self._find_dict_key_value_in_line(check_line, line_num)
                containers.extend(kv_values)

                # 更新括号计数
                dict_brace_count += check_line.count('{') - check_line.count('}')
                if dict_brace_count <= 0:
                    in_dict = False
                    dict_brace_count = 0

            # 检测多行数组开始 @[ 且未闭合
            if '@[' in check_line:
                after_at_bracket = check_line[check_line.find('@[') + 2:]
                open_brackets = 1 + after_at_bracket.count('[')
                close_brackets = after_at_bracket.count(']')
                if open_brackets > close_brackets:
                    in_array = True
                    array_bracket_count = open_brackets - close_brackets

            # 如果在多行数组内，检测元素
            elif in_array:
                array_values = self._find_array_element_in_line(check_line, line_num)
                containers.extend(array_values)

                array_bracket_count += check_line.count('[') - check_line.count(']')
                if array_bracket_count <= 0:
                    in_array = False
                    array_bracket_count = 0

        return containers

    def _find_dict_key_value_in_line(self, line: str, line_num: int) -> List[dict]:
        """在多行字典中检测键值对"""
        containers = []

        # 匹配 @"key": value 模式
        pattern = re.compile(r'@"[^"]*"\s*:\s*([^,}\n]+)')
        for match in pattern.finditer(line):
            value = match.group(1).strip()
            if value:
                col = match.start(1) + 1
                containers.append({
                    'type': 'dict',
                    'line': line_num,
                    'values': [{'value': value, 'column': col}]
                })

        return containers

    def _find_array_element_in_line(self, line: str, line_num: int) -> List[dict]:
        """在多行数组中检测元素"""
        containers = []

        # 按逗号分割元素，跳过空白
        elements = self._split_by_comma(line)
        col_offset = 1

        for elem in elements:
            elem = elem.strip()
            if elem and not elem.startswith(']'):
                # 计算列位置
                elem_pos = line.find(elem)
                containers.append({
                    'type': 'array',
                    'line': line_num,
                    'values': [{'value': elem, 'column': elem_pos + 1 if elem_pos >= 0 else col_offset}]
                })

        return containers

    def _find_dict_literals(self, line: str, line_num: int) -> List[dict]:
        """查找行中的字典字面量"""
        containers = []
        i = 0

        while i < len(line):
            # 查找 @{
            if i < len(line) - 1 and line[i:i+2] == '@{':
                start = i
                # 找到匹配的 }
                content_start = i + 2
                brace_count = 1
                j = content_start

                while j < len(line) and brace_count > 0:
                    if line[j] == '{':
                        brace_count += 1
                    elif line[j] == '}':
                        brace_count -= 1
                    j += 1

                if brace_count == 0:
                    # 提取字典内容
                    dict_content = line[content_start:j-1]
                    values = self._parse_dict_values(dict_content, start + 2)
                    if values:
                        containers.append({
                            'type': 'dict',
                            'line': line_num,
                            'values': values
                        })
                    i = j
                    continue
            i += 1

        return containers

    def _find_array_literals(self, line: str, line_num: int) -> List[dict]:
        """查找行中的数组字面量"""
        containers = []
        i = 0

        while i < len(line):
            # 查找 @[
            if i < len(line) - 1 and line[i:i+2] == '@[':
                start = i
                # 找到匹配的 ]
                content_start = i + 2
                bracket_count = 1
                j = content_start

                while j < len(line) and bracket_count > 0:
                    if line[j] == '[':
                        bracket_count += 1
                    elif line[j] == ']':
                        bracket_count -= 1
                    j += 1

                if bracket_count == 0:
                    # 提取数组内容
                    array_content = line[content_start:j-1]
                    values = self._parse_array_values(array_content, start + 2)
                    if values:
                        containers.append({
                            'type': 'array',
                            'line': line_num,
                            'values': values
                        })
                    i = j
                    continue
            i += 1

        return containers

    def _parse_dict_values(self, content: str, base_col: int) -> List[dict]:
        """解析字典内容，提取所有值"""
        values = []

        if not content.strip():
            return values

        # 按逗号分割键值对（注意处理嵌套）
        pairs = self._split_by_comma(content)

        for pair in pairs:
            pair = pair.strip()
            if not pair:
                continue

            # 找到冒号分隔键和值
            colon_pos = self._find_colon_separator(pair)
            if colon_pos != -1:
                value = pair[colon_pos + 1:].strip()
                # 计算值的列位置
                value_col = base_col + content.find(pair) + colon_pos + 1
                while value_col < len(content) + base_col and content[value_col - base_col:value_col - base_col + 1] in ' \t':
                    value_col += 1

                if value:
                    values.append({
                        'value': value,
                        'column': value_col + 1
                    })

        return values

    def _parse_array_values(self, content: str, base_col: int) -> List[dict]:
        """解析数组内容，提取所有元素"""
        values = []

        if not content.strip():
            return values

        # 按逗号分割元素（注意处理嵌套）
        elements = self._split_by_comma(content)

        for element in elements:
            element = element.strip()
            if not element:
                continue

            # 计算元素的列位置
            elem_col = base_col + content.find(element)

            values.append({
                'value': element,
                'column': elem_col + 1
            })

        return values

    def _split_by_comma(self, content: str) -> List[str]:
        """按逗号分割，但忽略嵌套结构中的逗号"""
        result = []
        current = []
        depth = 0  # 跟踪嵌套深度 (括号、方括号、大括号)
        in_string = False
        escape_next = False

        for char in content:
            if escape_next:
                current.append(char)
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                current.append(char)
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                current.append(char)
                continue

            if in_string:
                current.append(char)
                continue

            if char in '([{':
                depth += 1
                current.append(char)
            elif char in ')]}':
                depth -= 1
                current.append(char)
            elif char == ',' and depth == 0:
                result.append(''.join(current))
                current = []
            else:
                current.append(char)

        if current:
            result.append(''.join(current))

        return result

    def _find_colon_separator(self, pair: str) -> int:
        """找到键值对中的冒号分隔符位置（忽略嵌套中的冒号）"""
        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(pair):
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

            if char in '([{':
                depth += 1
            elif char in ')]}':
                depth -= 1
            elif char == ':' and depth == 0:
                return i

        return -1

    def _is_safe_value(self, value: str) -> Tuple[bool, Optional[str]]:
        """
        判断值是否安全（一定非 nil）

        Returns:
            (is_safe, unsafe_part): is_safe 为 True 表示安全，
            unsafe_part 为需要警告的不安全部分（用于三目运算符场景）
        """
        value = value.strip()

        if not value:
            return True, None

        # 检查是否匹配安全模式
        for pattern in self.SAFE_VALUE_PATTERNS:
            if pattern.match(value):
                return True, None

        # 检查三目运算符
        ternary_result = self._check_ternary_operator(value)
        if ternary_result is not None:
            return ternary_result

        return False, None

    def _check_ternary_operator(self, value: str) -> Optional[Tuple[bool, Optional[str]]]:
        """
        检查三目运算符表达式

        支持的格式：
        - someValue ?: defaultValue (Elvis 运算符)
        - someValue ? trueValue : falseValue (标准三目)

        Returns:
            None: 不是三目运算符
            (True, None): 安全（默认值是字面量）
            (False, unsafe_part): 不安全，返回需要警告的部分
        """
        # 查找 ? 的位置（忽略嵌套结构中的 ?）
        question_pos = self._find_operator_position(value, '?')
        if question_pos == -1:
            return None

        # 检查是否是 Elvis 运算符 (?:)
        after_question = value[question_pos + 1:].lstrip()
        if after_question.startswith(':'):
            # Elvis 运算符: someValue ?: defaultValue
            default_value = after_question[1:].strip()
            is_safe, _ = self._is_literal_safe(default_value)
            if is_safe:
                return True, None
            else:
                return False, default_value
        else:
            # 标准三目: someValue ? trueValue : falseValue
            # 两个分支都可能被返回，所以两个都要检查
            colon_pos = self._find_operator_position(value[question_pos + 1:], ':')
            if colon_pos == -1:
                return None

            # 实际的冒号位置
            actual_colon_pos = question_pos + 1 + colon_pos
            true_value = value[question_pos + 1:actual_colon_pos].strip()
            false_value = value[actual_colon_pos + 1:].strip()

            # 两个分支都必须安全
            true_safe, _ = self._is_literal_safe(true_value)
            false_safe, _ = self._is_literal_safe(false_value)

            if true_safe and false_safe:
                return True, None
            elif not true_safe:
                return False, true_value
            else:
                return False, false_value

    def _find_operator_position(self, text: str, operator: str) -> int:
        """查找运算符位置（忽略嵌套结构和字符串中的）"""
        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text):
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

            if char in '([{':
                depth += 1
            elif char in ')]}':
                depth -= 1
            elif char == operator and depth == 0:
                return i

        return -1

    def _is_literal_safe(self, value: str) -> Tuple[bool, None]:
        """检查值是否是字面量（用于三目运算符检查）"""
        value = value.strip()

        if not value:
            return True, None

        for pattern in self.SAFE_VALUE_PATTERNS:
            if pattern.match(value):
                return True, None

        # 递归检查嵌套的三目运算符
        ternary_result = self._check_ternary_operator(value)
        if ternary_result is not None:
            return ternary_result

        return False, None
