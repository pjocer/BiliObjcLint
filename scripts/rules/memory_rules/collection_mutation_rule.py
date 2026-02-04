"""
Collection Mutation Rule - 集合修改操作安全检查
"""
import re
from typing import List, Set

from ..base_rule import BaseRule
from core.lint.reporter import Violation, Severity


class CollectionMutationRule(BaseRule):
    """集合修改操作安全检查

    检测以下场景：
    1. dict[key] = value - 字典下标赋值，需确认 key 不为空
    2. array[index] = value - 数组下标赋值，禁止使用，应使用 addObject: 等方法
    3. [array addObject:value] - 需确认 value 不为空
    4. [array insertObject:value atIndex:] - 需确认 value 不为空
    5. [array replaceObjectAtIndex:index withObject:value] - 需确认 value 不为空
    """

    identifier = "collection_mutation"
    name = "Collection Mutation Safety Check"
    description = "检查集合修改操作的安全性"
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

    # 安全的值模式（与 WrapperEmptyPointerRule 相同）
    SAFE_VALUE_PATTERNS = [
        re.compile(r'^@".*"$'),           # 字符串字面量
        re.compile(r'^@\d+\.?\d*$'),      # 数字字面量
        re.compile(r'^@\(.+\)$'),         # 装箱表达式
        re.compile(r'^@(YES|NO|TRUE|FALSE|true|false)$'),  # 布尔字面量
        re.compile(r'^@\{.*\}$'),         # 嵌套字典
        re.compile(r'^@\[.*\]$'),         # 嵌套数组
    ]

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

            # 1. 检测数组下标赋值（错误用法）
            array_match = self.ARRAY_SUBSCRIPT_PATTERN.search(check_line)
            if array_match:
                violations.append(self._create_violation_with_severity(
                    file_path=file_path,
                    line=line_num,
                    column=array_match.start() + 1,
                    message="禁止使用数组下标赋值，请使用 `addObject:`、`insertObject:atIndex:` 或 `replaceObjectAtIndex:withObject:` 方法",
                    severity=Severity.ERROR
                ))
                continue  # 跳过后续检测，避免重复报告

            # 2. 检测字典下标赋值
            dict_match = self.DICT_SUBSCRIPT_PATTERN.search(check_line)
            if dict_match:
                key = dict_match.group(2).strip()
                if not self._is_safe_key(key):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=dict_match.start(2) + 1,
                        message=f"字典下标赋值时请确认 key '{key}' 不为 nil"
                    ))

            # 3. 检测 addObject:
            add_match = self.ADD_OBJECT_PATTERN.search(check_line)
            if add_match:
                value = add_match.group(2).strip()
                if not self._is_safe_value(value):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=add_match.start(2) + 1,
                        message=f"请确认 '{value}' 不为 nil"
                    ))

            # 4. 检测 insertObject:atIndex:
            insert_match = self.INSERT_OBJECT_PATTERN.search(check_line)
            if insert_match:
                value = insert_match.group(2).strip()
                if not self._is_safe_value(value):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=insert_match.start(2) + 1,
                        message=f"请确认 '{value}' 不为 nil"
                    ))

            # 5. 检测 replaceObjectAtIndex:withObject:
            replace_match = self.REPLACE_OBJECT_PATTERN.search(check_line)
            if replace_match:
                value = replace_match.group(2).strip()
                if not self._is_safe_value(value):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=replace_match.start(2) + 1,
                        message=f"请确认 '{value}' 不为 nil"
                    ))

        return violations

    def _create_violation_with_severity(self, file_path: str, line: int, column: int,
                                        message: str, severity: Severity) -> Violation:
        """创建带自定义 severity 的 violation"""
        return Violation(
            file_path=file_path,
            line=line,
            column=column,
            severity=severity,
            message=message,
            rule_id=self.identifier,
            source='biliobjclint'
        )

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

        for pattern in self.SAFE_VALUE_PATTERNS:
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
