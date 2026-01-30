"""
Memory Rules - 内存相关规则
"""
import re
from typing import List, Set, Optional, Tuple
from dataclasses import dataclass

from .base_rule import BaseRule
from core.reporter import Violation, Severity


class WeakDelegateRule(BaseRule):
    """delegate 应使用 weak 属性"""

    identifier = "weak_delegate"
    name = "Weak Delegate Check"
    description = "检查 delegate 属性是否使用 weak 修饰"
    default_severity = "error"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 匹配 delegate 属性声明
        # @property (nonatomic, strong) id<XXXDelegate> delegate;
        pattern = r'@property\s*\(([^)]*)\)[^;]*\b(\w*[dD]elegate)\s*;'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            match = re.search(pattern, line)
            if match:
                modifiers = match.group(1).lower()
                prop_name = match.group(2)

                # 检查是否有 weak 修饰符
                if 'weak' not in modifiers:
                    # 检查是否有 strong/retain/copy（不应该用于 delegate）
                    if any(m in modifiers for m in ['strong', 'retain', 'copy']):
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=match.start(2) + 1,
                            message=f"'{prop_name}' 应使用 weak 修饰以避免循环引用"
                        ))
                    elif 'assign' not in modifiers:
                        # 如果既不是 weak 也不是 assign，给出提示
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=match.start(2) + 1,
                            message=f"'{prop_name}' 建议使用 weak 修饰"
                        ))

        return violations


@dataclass
class WeakDeclaration:
    """Weak 声明信息"""
    line_num: int
    var_name: str  # 变量名，如 wSelf, weakSelf, self_weak_ (for @weakify)
    is_macro: bool  # 是否为 @weakify 宏


@dataclass
class StrongDeclaration:
    """Strong 声明信息"""
    line_num: int
    var_name: str  # 变量名，如 sSelf, strongSelf, self (for @strongify)
    is_macro: bool  # 是否为 @strongify 宏


class BlockRetainCycleRule(BaseRule):
    """Block 循环引用检查（合并 strong_self_in_block）"""

    identifier = "block_retain_cycle"
    name = "Block Retain Cycle Check"
    description = "检测 Block 中可能的循环引用，检查 weak/strong self 使用"
    default_severity = "warning"

    # 正则表达式
    # Manual weak: __weak typeof(self) xxx = self (支持无空格)
    WEAK_MANUAL_PATTERN = re.compile(
        r'__weak\s+(?:typeof|__typeof|__typeof__)\s*\(\s*self\s*\)\s*(\w+)\s*=\s*self'
    )
    # @weakify(self) 或 @weakify(self, other)
    WEAK_MACRO_PATTERN = re.compile(r'@weakify\s*\([^)]*\bself\b[^)]*\)')

    # Manual strong: __strong typeof(weakVar) xxx = weakVar (支持无空格)
    STRONG_MANUAL_PATTERN = re.compile(
        r'__strong\s+(?:typeof|__typeof|__typeof__)\s*\(\s*(\w+)\s*\)\s*(\w+)\s*=\s*\1'
    )
    # @strongify(self)
    STRONG_MACRO_PATTERN = re.compile(r'@strongify\s*\([^)]*\bself\b[^)]*\)')

    # Block 开始检测
    BLOCK_START_PATTERN = re.compile(r'\^\s*[\(\{]')

    # 方法定义开始
    METHOD_START_PATTERN = re.compile(r'^[-+]\s*\([^)]+\)')

    # self 使用检测 (排除注释和字符串)
    SELF_USAGE_PATTERN = re.compile(r'(?<!\w)self(?:\.|\s*->|\s*\]|\s+\w)')

    # C 函数检测 (dispatch_async, dispatch_after, dispatch_once 等)
    C_FUNCTION_PATTERN = re.compile(r'\bdispatch_(?:async|after|once|sync|barrier_async|barrier_sync|apply)\s*\(')

    # 类方法调用检测 (receiver 以大写字母开头)
    CLASS_METHOD_PATTERN = re.compile(r'\[\s*([A-Z][A-Za-z0-9]*)\s+\w+')

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 逐行分析
        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 跳过注释行
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            # 检测 self 使用
            if not self._line_contains_self(line):
                continue

            # 检测是否在 block 内
            if not self._is_in_block(lines, line_num):
                continue

            # 检测 self 的具体使用位置和类型
            self_usages = self._find_self_usages(line)
            if not self_usages:
                continue

            # 获取当前方法的作用域
            method_start = self._find_method_start(lines, line_num)

            # 在方法作用域内查找 weak/strong 声明
            weak_decls = self._find_weak_declarations(lines, method_start, line_num)
            strong_decls = self._find_strong_declarations(lines, method_start, line_num)

            # 检测混用 warning
            if self._has_mixed_usage(weak_decls):
                violations.append(self._create_violation_with_severity(
                    file_path=file_path,
                    line=line_num,
                    column=1,
                    message="不建议混用 __weak typeof(self) 和 @weakify(self)，请保持一致性",
                    severity=Severity.WARNING
                ))

            # 检测 block 调用上下文
            block_context = self._get_block_context(lines, line_num)

            # 对每个 self 使用进行检查
            for col, usage_type in self_usages:
                violation = self._check_self_usage(
                    file_path=file_path,
                    line_num=line_num,
                    column=col,
                    usage_type=usage_type,
                    weak_decls=weak_decls,
                    strong_decls=strong_decls,
                    block_context=block_context,
                    line=line
                )
                if violation:
                    violations.append(violation)

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

    def _line_contains_self(self, line: str) -> bool:
        """检查行是否包含 self（排除注释和字符串中的）"""
        # 简单检查，后续会更精确过滤（不区分大小写以匹配 wSelf, weakSelf 等）
        line_lower = line.lower()
        if 'self' not in line_lower:
            return False

        # 排除注释
        comment_pos = line.find('//')
        if comment_pos != -1:
            self_pos = line_lower.find('self')
            if self_pos > comment_pos:
                return False

        return True

    def _is_in_block(self, lines: List[str], line_num: int) -> bool:
        """检测当前行是否在 block 内"""
        # 向上查找 block 开始标记
        # line_num 是 1-indexed，lines 是 0-indexed
        # 从当前行的上一行开始往上查找
        brace_count = 0
        found_block_start = False

        # 先检查当前行是否同时包含 block 开始和 self 使用
        current_line = lines[line_num - 1] if line_num > 0 else ''
        if self.BLOCK_START_PATTERN.search(current_line):
            # 当前行有 block 开始，检查 self 是否在 ^{ 之后
            block_match = self.BLOCK_START_PATTERN.search(current_line)
            if block_match:
                after_block = current_line[block_match.end():]
                if 'self' in after_block:
                    return True

        for i in range(line_num - 2, max(0, line_num - 100), -1):
            line = lines[i]

            # 如果遇到方法定义，停止搜索（已离开当前方法作用域）
            if self.METHOD_START_PATTERN.match(line.strip()):
                break

            # 计算大括号（向上扫描时，} 表示进入作用域，{ 表示离开作用域）
            brace_count += line.count('}') - line.count('{')

            # 检测 block 开始
            if self.BLOCK_START_PATTERN.search(line):
                # 只有当 brace_count < 0 时，说明该 block 的 { 还未被关闭
                # brace_count = 0 表示 block 已经被对应的 } 关闭了
                if brace_count < 0:
                    found_block_start = True
                    break

        return found_block_start

    def _find_method_start(self, lines: List[str], line_num: int) -> int:
        """查找当前行所属方法的起始行号"""
        for i in range(line_num - 1, -1, -1):
            if self.METHOD_START_PATTERN.match(lines[i].strip()):
                return i + 1  # 返回 1-based 行号
        return 1  # 如果找不到，返回文件开头

    def _strip_comment(self, line: str) -> str:
        """移除行尾注释"""
        comment_pos = line.find('//')
        return line[:comment_pos] if comment_pos != -1 else line

    def _find_weak_declarations(self, lines: List[str], start_line: int, end_line: int) -> List[WeakDeclaration]:
        """在指定范围内查找 weak 声明"""
        declarations = []

        for i in range(start_line - 1, end_line - 1):  # 转换为 0-based
            line = self._strip_comment(lines[i])

            # 检测 manual weak
            match = self.WEAK_MANUAL_PATTERN.search(line)
            if match:
                declarations.append(WeakDeclaration(
                    line_num=i + 1,
                    var_name=match.group(1),
                    is_macro=False
                ))

            # 检测 @weakify
            if self.WEAK_MACRO_PATTERN.search(line):
                declarations.append(WeakDeclaration(
                    line_num=i + 1,
                    var_name='self_weak_',  # @weakify 生成的变量名
                    is_macro=True
                ))

        return declarations

    def _find_strong_declarations(self, lines: List[str], start_line: int, end_line: int) -> List[StrongDeclaration]:
        """在指定范围内查找 strong 声明"""
        declarations = []

        for i in range(start_line - 1, end_line):  # 转换为 0-based，包含当前行
            line = self._strip_comment(lines[i])

            # 检测 manual strong
            match = self.STRONG_MANUAL_PATTERN.search(line)
            if match:
                declarations.append(StrongDeclaration(
                    line_num=i + 1,
                    var_name=match.group(2),
                    is_macro=False
                ))

            # 检测 @strongify
            if self.STRONG_MACRO_PATTERN.search(line):
                declarations.append(StrongDeclaration(
                    line_num=i + 1,
                    var_name='self',  # @strongify shadow self
                    is_macro=True
                ))

        return declarations

    def _has_mixed_usage(self, weak_decls: List[WeakDeclaration]) -> bool:
        """检测是否混用 manual 和 macro"""
        has_manual = any(not d.is_macro for d in weak_decls)
        has_macro = any(d.is_macro for d in weak_decls)
        return has_manual and has_macro

    def _get_block_context(self, lines: List[str], line_num: int) -> str:
        """
        获取 block 的调用上下文
        返回: 'c_function' | 'class_method' | 'instance_method'
        """
        # 向上查找包含 block 的方法调用
        # 不在 block 开始处停止，继续查找外层上下文
        # line_num 是 1-indexed，lines 是 0-indexed
        for i in range(line_num - 2, max(0, line_num - 30), -1):
            line = lines[i]

            # 如果遇到方法定义，停止搜索
            if self.METHOD_START_PATTERN.match(line.strip()):
                break

            # 检测 C 函数
            if self.C_FUNCTION_PATTERN.search(line):
                return 'c_function'

            # 检测类方法调用（同一行内的类方法调用）
            class_match = self.CLASS_METHOD_PATTERN.search(line)
            if class_match:
                # 确保这不是在 block 内部的类方法调用
                # 检查这行是否同时有 block 开始
                if not self.BLOCK_START_PATTERN.search(line[:class_match.start()]):
                    return 'class_method'

        return 'instance_method'

    def _find_self_usages(self, line: str) -> List[Tuple[int, str]]:
        """
        查找行中所有 self 使用
        返回: [(column, usage_type), ...]
        usage_type: 'self' | 'weak_var' | 'strong_var' | 'self_weak_'
        """
        usages = []

        # 跳过注释部分
        comment_pos = line.find('//')
        check_line = line[:comment_pos] if comment_pos != -1 else line

        # 跳过 weak/strong 声明行
        if self.WEAK_MANUAL_PATTERN.search(check_line) or self.STRONG_MANUAL_PATTERN.search(check_line):
            return usages

        # 如果行包含 block 开始 (^{)，只检查 ^{ 之后的部分
        block_start_match = self.BLOCK_START_PATTERN.search(check_line)
        if block_start_match:
            # 只检查 block 开始之后的部分
            check_line = check_line[block_start_match.end():]
            col_offset = block_start_match.end()
        else:
            col_offset = 0

        # 查找 self 使用
        for match in re.finditer(r'(?<!\w)(self|self_weak_|\w*[sS]elf)\b', check_line):
            word = match.group(1)
            col = match.start(1) + 1 + col_offset

            # 跳过 typeof(self) 中的 self
            context_before = check_line[max(0, match.start() - 10):match.start()]
            if 'typeof(' in context_before or 'typeof (' in context_before:
                continue

            # 跳过 = self 赋值语句右侧的 self
            context_after = check_line[match.end():match.end() + 5]
            context_full = check_line[max(0, match.start() - 3):match.end() + 3]
            if '= ' + word in context_full or '=' + word in context_full:
                # 这是赋值语句的右侧
                continue

            # 分类
            if word == 'self':
                usages.append((col, 'self'))
            elif word == 'self_weak_':
                usages.append((col, 'self_weak_'))
            elif 'weak' in word.lower() or (word.startswith('w') and 'Self' in word):
                usages.append((col, 'weak_var'))
            elif 'strong' in word.lower() or (word.startswith('s') and 'Self' in word):
                usages.append((col, 'strong_var'))

        return usages

    def _check_self_usage(self, file_path: str, line_num: int, column: int,
                          usage_type: str, weak_decls: List[WeakDeclaration],
                          strong_decls: List[StrongDeclaration],
                          block_context: str, line: str) -> Optional[Violation]:
        """
        检查单个 self 使用是否违规

        Returns:
            Violation 或 None
        """
        has_manual_weak = any(not d.is_macro for d in weak_decls)
        has_macro_weak = any(d.is_macro for d in weak_decls)
        has_weak = len(weak_decls) > 0

        has_manual_strong = any(not d.is_macro for d in strong_decls)
        has_macro_strong = any(d.is_macro for d in strong_decls)
        has_strong = len(strong_decls) > 0

        # 规则 0: C 函数中的 block -> WARNING 或不检测
        if block_context == 'c_function':
            if usage_type == 'self':
                return self._create_violation_with_severity(
                    file_path=file_path,
                    line=line_num,
                    column=column,
                    message="C 函数 (dispatch_async 等) 中使用 self 通常安全，但建议确认",
                    severity=Severity.WARNING
                )
            return None  # 其他情况 OK

        # 规则 1: 类方法调用中的 block -> WARNING
        if block_context == 'class_method':
            if usage_type == 'self' and not has_weak:
                return self._create_violation_with_severity(
                    file_path=file_path,
                    line=line_num,
                    column=column,
                    message="类方法中使用 self 可能安全，但建议使用 weakSelf 以确保无循环引用",
                    severity=Severity.WARNING
                )
            return None  # 类方法中其他情况 OK

        # 以下为实例方法中的检测

        # 规则 2: 无 weak 转换 -> ERROR
        if not has_weak:
            if usage_type == 'self':
                return self._create_violation_with_severity(
                    file_path=file_path,
                    line=line_num,
                    column=column,
                    message="Block 内直接使用 self 可能导致循环引用，必须使用 weakSelf",
                    severity=Severity.ERROR
                )

        # 规则 3: 使用 manual weak 方式
        if has_manual_weak:
            weak_var_name = next((d.var_name for d in weak_decls if not d.is_macro), None)
            strong_var_name = next((d.var_name for d in strong_decls if not d.is_macro), None)

            if usage_type == 'self':
                # 有 weak 但使用了 self -> ERROR
                if has_strong:
                    return self._create_violation_with_severity(
                        file_path=file_path,
                        line=line_num,
                        column=column,
                        message=f"已声明 {strong_var_name or 'strongSelf'}，应使用它而不是 self",
                        severity=Severity.ERROR
                    )
                else:
                    return self._create_violation_with_severity(
                        file_path=file_path,
                        line=line_num,
                        column=column,
                        message=f"已声明 {weak_var_name}，应使用它而不是 self",
                        severity=Severity.ERROR
                    )

            elif usage_type == 'weak_var':
                # 使用 weak 变量
                if has_strong:
                    # 有 strong 但用了 weak -> WARNING
                    return self._create_violation_with_severity(
                        file_path=file_path,
                        line=line_num,
                        column=column,
                        message=f"已声明 {strong_var_name or 'strongSelf'}，建议使用它而不是 weakSelf",
                        severity=Severity.WARNING
                    )
                else:
                    # 无 strong，用 weak -> WARNING
                    return self._create_violation_with_severity(
                        file_path=file_path,
                        line=line_num,
                        column=column,
                        message="使用 weakSelf 时建议先转为 strongSelf 并检查是否为 nil",
                        severity=Severity.WARNING
                    )

            elif usage_type == 'strong_var':
                # 使用 strong 变量 -> OK
                return None

        # 规则 4: 使用 @weakify 方式
        if has_macro_weak:
            if usage_type == 'self':
                if has_macro_strong:
                    # 有 @strongify，使用 self -> OK (self 已被 shadow)
                    return None
                else:
                    # 无 @strongify，使用 self -> ERROR
                    return self._create_violation_with_severity(
                        file_path=file_path,
                        line=line_num,
                        column=column,
                        message="使用 @weakify 后应在 block 内添加 @strongify(self)，或使用 self_weak_",
                        severity=Severity.ERROR
                    )

            elif usage_type == 'self_weak_':
                # 使用 self_weak_ -> WARNING (建议用 @strongify)
                return self._create_violation_with_severity(
                    file_path=file_path,
                    line=line_num,
                    column=column,
                    message="建议添加 @strongify(self) 而不是直接使用 self_weak_",
                    severity=Severity.WARNING
                )

        return None


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
        """查找所有容器字面量及其内容"""
        containers = []

        for line_num, line in enumerate(lines, 1):
            # 跳过注释
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            # 移除行尾注释
            comment_pos = line.find('//')
            check_line = line[:comment_pos] if comment_pos != -1 else line

            # 查找字典字面量 @{...}
            dict_containers = self._find_dict_literals(check_line, line_num)
            containers.extend(dict_containers)

            # 查找数组字面量 @[...]
            array_containers = self._find_array_literals(check_line, line_num)
            containers.extend(array_containers)

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


class DictUsageRule(BaseRule):
    """字典方法使用检查

    检测 -[NSMutableDictionary setObject:forKey:] 的使用，
    建议使用 setValue:forKey: 替代以避免 nil 崩溃。
    """

    identifier = "dict_usage"
    name = "Dictionary Usage Check"
    description = "检查 NSMutableDictionary 的 setObject:forKey: 使用"
    default_severity = "warning"

    # 匹配 setObject:forKey: 方法调用
    # 例如: [dict setObject:value forKey:key]
    #       [self.dict setObject:value forKey:key]
    SET_OBJECT_PATTERN = re.compile(
        r'\[\s*\S+\s+setObject\s*:\s*\S+\s+forKey\s*:'
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

            # 检测 setObject:forKey: 使用
            match = self.SET_OBJECT_PATTERN.search(check_line)
            if match:
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=match.start() + 1,
                    message="请确认 object 非空，建议使用 `setValue:forKey:` 替代"
                ))

        return violations


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
