"""
Collection Mutation Rule - 集合修改操作安全检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from ..rule_utils import SAFE_VALUE_PATTERNS
from core.lint.reporter import Violation, Severity, ViolationType


# SubType 定义
class SubType:
    """collection_mutation 规则的子类型"""
    ARRAY_NUMERIC_SUBSCRIPT = ViolationType(
        "array_numeric_subscript",
        "禁止使用数组下标赋值，请使用 `addObject:`、`insertObject:atIndex:` 或 `replaceObjectAtIndex:withObject:` 方法",
        Severity.ERROR
    )
    ARRAY_VAR_SUBSCRIPT = ViolationType(
        "array_var_subscript",
        "数组 '{var}' 下标赋值使用变量索引 '{index}'，请确认索引有效，建议使用安全方法替代"
    )
    DICT_KEY_NIL = ViolationType(
        "dict_key_nil",
        "字典下标赋值时请确认 key '{key}' 不为 nil"
    )
    ADD_OBJECT_NIL = ViolationType(
        "add_object_nil",
        "请确认 '{value}' 不为 nil"
    )
    INSERT_OBJECT_NIL = ViolationType(
        "insert_object_nil",
        "请确认 '{value}' 不为 nil"
    )
    REPLACE_OBJECT_NIL = ViolationType(
        "replace_object_nil",
        "请确认 '{value}' 不为 nil"
    )


class CollectionMutationRule(BaseRule):
    """集合修改操作安全检查

    检测以下场景：
    1. dict[key] = value - 字典下标赋值，需确认 key 不为空
    2. array[index] = value - 数组下标赋值（数字索引），禁止使用
    3. array[var] = value - 数组下标赋值（变量索引），给警告
    4. [array addObject:value] - 需确认 value 不为空
    5. [array insertObject:value atIndex:] - 需确认 value 不为空
    6. [array replaceObjectAtIndex:index withObject:value] - 需确认 value 不为空
    """

    identifier = "collection_mutation"
    name = "Collection Mutation Safety Check"
    description = "检查集合修改操作的安全性"
    display_name = "集合变异"
    default_severity = "warning"

    # 字典下标赋值: dict[key] = value 或 self.dict[key] = value
    # 匹配变量名后跟 [xxx] = ，排除数组声明如 NSArray *arr = @[...]
    DICT_SUBSCRIPT_PATTERN = re.compile(
        r'(\w+(?:\.\w+)*)\s*\[\s*([^\]]+)\s*\]\s*='
    )

    # 数组下标赋值: array[0] = value（这是错误用法）
    # 检测下标是数字的情况
    ARRAY_SUBSCRIPT_PATTERN = re.compile(
        r'(\w+(?:\.\w+)*)\s*\[\s*(\d+)\s*\]\s*='
    )

    # 数组变量下标赋值: array[index] = value（警告用法）
    # 检测下标是变量的情况
    ARRAY_VAR_SUBSCRIPT_PATTERN = re.compile(
        r'(\w+(?:\.\w+)*)\s*\[\s*([a-zA-Z_]\w*)\s*\]\s*='
    )

    # addObject: 方法
    ADD_OBJECT_PATTERN = re.compile(
        r'\[\s*(\S+)\s+addObject\s*:\s*([^\]]+)\s*\]'
    )

    # insertObject:atIndex: 方法
    INSERT_OBJECT_PATTERN = re.compile(
        r'\[\s*(\S+)\s+insertObject\s*:\s*([^\]]+?)\s+atIndex\s*:'
    )

    # replaceObjectAtIndex:withObject: 方法
    REPLACE_OBJECT_PATTERN = re.compile(
        r'\[\s*(\S+)\s+replaceObjectAtIndex\s*:\s*\S+\s+withObject\s*:\s*([^\]]+)\s*\]'
    )

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        del content  # unused
        violations = []

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 跳过注释行
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            # 移除行尾注释
            comment_pos = line.find('//')
            check_line = line[:comment_pos] if comment_pos != -1 else line

            # 跳过变量声明行（如 NSArray *arr = @[...]）
            if self._is_variable_declaration(check_line):
                continue

            # 获取 related_lines（单行）
            related_lines = self.get_related_lines(file_path, line_num, lines)

            # 1. 检测数组数字下标赋值（错误用法）
            array_match = self.ARRAY_SUBSCRIPT_PATTERN.search(check_line)
            if array_match:
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=array_match.start() + 1,
                    lines=lines,
                    violation_type=SubType.ARRAY_NUMERIC_SUBSCRIPT,
                    related_lines=related_lines
                ))
                continue  # 跳过后续检测，避免重复报告

            # 2. 检测数组变量下标赋值（警告用法）
            array_var_match = self.ARRAY_VAR_SUBSCRIPT_PATTERN.search(check_line)
            if array_var_match:
                var_name = array_var_match.group(1)
                index_var = array_var_match.group(2)
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=array_var_match.start() + 1,
                    lines=lines,
                    violation_type=SubType.ARRAY_VAR_SUBSCRIPT,
                    related_lines=related_lines,
                    message_vars={"var": var_name, "index": index_var}
                ))
                continue  # 跳过后续检测，避免重复报告

            # 3. 检测字典下标赋值
            dict_match = self.DICT_SUBSCRIPT_PATTERN.search(check_line)
            if dict_match:
                key = dict_match.group(2).strip()
                if not self._is_safe_key(key):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=dict_match.start(2) + 1,
                        lines=lines,
                        violation_type=SubType.DICT_KEY_NIL,
                        related_lines=related_lines,
                        message_vars={"key": key}
                    ))

            # 4. 检测 addObject:
            add_match = self.ADD_OBJECT_PATTERN.search(check_line)
            if add_match:
                value = add_match.group(2).strip()
                if not self._is_safe_value(value):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=add_match.start(2) + 1,
                        lines=lines,
                        violation_type=SubType.ADD_OBJECT_NIL,
                        related_lines=related_lines,
                        message_vars={"value": value}
                    ))

            # 5. 检测 insertObject:atIndex:
            insert_match = self.INSERT_OBJECT_PATTERN.search(check_line)
            if insert_match:
                value = insert_match.group(2).strip()
                if not self._is_safe_value(value):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=insert_match.start(2) + 1,
                        lines=lines,
                        violation_type=SubType.INSERT_OBJECT_NIL,
                        related_lines=related_lines,
                        message_vars={"value": value}
                    ))

            # 6. 检测 replaceObjectAtIndex:withObject:
            replace_match = self.REPLACE_OBJECT_PATTERN.search(check_line)
            if replace_match:
                value = replace_match.group(2).strip()
                if not self._is_safe_value(value):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=replace_match.start(2) + 1,
                        lines=lines,
                        violation_type=SubType.REPLACE_OBJECT_NIL,
                        related_lines=related_lines,
                        message_vars={"value": value}
                    ))

        return violations

    def _is_variable_declaration(self, line: str) -> bool:
        """检查是否是变量声明行"""
        # 匹配类型声明模式: NSArray *, NSDictionary *, NSMutableArray * 等
        decl_pattern = re.compile(r'^\s*(NS\w+|__strong|__weak)\s*\*')
        return bool(decl_pattern.search(line))

    def _is_safe_key(self, key: str) -> bool:
        """检查字典 key 是否安全"""
        key = key.strip()

        # 字符串字面量是安全的
        if re.match(r'^@".*"$', key):
            return True

        # 常量（全大写或以 k 开头的驼峰）通常是安全的
        if re.match(r'^k[A-Z]\w*$', key) or re.match(r'^[A-Z][A-Z0-9_]+$', key):
            return True

        # 系统常量（NS 开头的常量）
        if re.match(r'^NS\w+$', key):
            return True

        # 检查三目运算符（Elvis 或标准三目）
        if '?' in key:
            return self._check_ternary_safe_key(key)

        return False

    def _check_ternary_safe_key(self, key: str) -> bool:
        """检查三目运算符作为 key 的安全性"""
        # 安全的 key 模式：字符串字面量、常量等
        safe_key_pattern = r'@"[^"]*"|k[A-Z]\w*|[A-Z][A-Z0-9_]+|NS\w+'

        # Elvis 运算符: someValue ?: @"default"
        # 只需检查 default 值是否是安全的 key
        elvis_match = re.search(r'\?\s*:\s*(' + safe_key_pattern + r')\s*$', key)
        if elvis_match:
            return True

        # 标准三目: cond ? trueKey : falseKey
        # 两个分支都必须是安全的 key 值
        ternary_match = re.search(r'\?\s*(' + safe_key_pattern + r')\s*:\s*(' + safe_key_pattern + r')\s*$', key)
        if ternary_match:
            return True

        return False

    def _is_safe_value(self, value: str) -> bool:
        """检查值是否安全"""
        value = value.strip()

        if not value:
            return True

        # 使用 rule_utils 中的 SAFE_VALUE_PATTERNS
        for pattern in SAFE_VALUE_PATTERNS:
            if pattern.match(value):
                return True

        # 检查三目运算符
        if '?' in value:
            return self._check_ternary_safe(value)

        return False

    def _check_ternary_safe(self, value: str) -> bool:
        """检查三目运算符的安全性"""
        literal_pattern = r'@"[^"]*"|@\d+\.?\d*|@\([^)]+\)|@YES|@NO|@\{[^}]*\}|@\[[^\]]*\]'

        # Elvis 运算符: someValue ?: @"default"
        # 只需检查 default 值是否安全
        elvis_match = re.search(r'\?\s*:\s*(' + literal_pattern + r')\s*$', value)
        if elvis_match:
            return True

        # 标准三目: cond ? trueValue : falseValue
        # 两个分支都必须是安全的字面量
        ternary_match = re.search(r'\?\s*(' + literal_pattern + r')\s*:\s*(' + literal_pattern + r')\s*$', value)
        if ternary_match:
            return True

        return False
