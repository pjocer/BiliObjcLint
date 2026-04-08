"""
Block Retain Cycle Rule - Block 循环引用检查
"""
import re
from typing import List, Set, Optional, Tuple
from dataclasses import dataclass

from ..base_rule import BaseRule
from ..rule_utils import get_method_range, strip_line_comment
from core.lint.reporter import Violation, Severity, ViolationType


# SubType 定义（sub_type + message + severity 绑定）
class SubType:
    """block_retain_cycle 规则的子类型"""
    # ERROR 级别
    DIRECT_SELF = ViolationType(
        "direct_self",
        "Block 内直接使用 self 可能导致循环引用，必须使用 weakSelf",
        Severity.ERROR
    )
    HAS_WEAK_USE_SELF = ViolationType(
        "has_weak_use_self",
        "已声明 {var}，应使用它而不是 self",
        Severity.ERROR
    )
    HAS_STRONG_USE_SELF = ViolationType(
        "has_strong_use_self",
        "已声明 {var}，应使用它而不是 self",
        Severity.ERROR
    )
    NEED_STRONGIFY = ViolationType(
        "need_strongify",
        "使用 @weakify 后应在 block 内添加 @strongify(self)，或使用 self_weak_",
        Severity.ERROR
    )
    # WARNING 级别
    WEAK_WITHOUT_STRONG = ViolationType(
        "weak_without_strong",
        "使用 weakSelf 时建议先转为 strongSelf 并检查是否为 nil"
    )
    HAS_STRONG_USE_WEAK = ViolationType(
        "has_strong_use_weak",
        "已声明 {var}，建议使用它而不是 weakSelf"
    )
    MIXED_WEAK_STYLE = ViolationType(
        "mixed_weak_style",
        "不建议混用 __weak typeof(self) 和 @weakify(self)，请保持一致性"
    )
    SELF_WEAK_USAGE = ViolationType(
        "self_weak_usage",
        "建议添加 @strongify(self) 而不是直接使用 self_weak_"
    )
    C_FUNCTION_SELF = ViolationType(
        "c_function_self",
        "C 函数 (dispatch_async 等) 中使用 self 通常安全，但建议确认"
    )
    CLASS_METHOD_SELF = ViolationType(
        "class_method_self",
        "类方法中使用 self 可能安全，但建议使用 weakSelf 以确保无循环引用"
    )
    BLOCK_SELF = ViolationType(
        "block_self",
        "__block 修饰的 self 引用在 ARC 下仍为强引用，可能导致循环引用"
    )
    TIMER_BLOCK_SELF = ViolationType(
        "timer_block_self",
        "NSTimer 会持有 block，block 内使用 self 可能导致循环引用",
        Severity.ERROR
    )


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
    display_name = "循环引用"
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

    # Block 开始检测：支持 ^{, ^(, ^ReturnType(, ^ReturnType { 等形式
    BLOCK_START_PATTERN = re.compile(r'\^\s*(?:[A-Za-z_]\w*\s*)?[\(\{]')

    # 方法定义开始
    METHOD_START_PATTERN = re.compile(r'^[-+]\s*\([^)]+\)')

    # self 使用检测 (排除注释和字符串)
    SELF_USAGE_PATTERN = re.compile(r'(?<!\w)self(?:\.|\s*->|\s*\]|\s+\w)')

    # C 函数检测 (dispatch_async, dispatch_after, dispatch_once, dispatch_group_notify 等)
    C_FUNCTION_PATTERN = re.compile(r'\bdispatch_(?:async|after|once|sync|barrier_async|barrier_sync|apply|group_notify|group_async)\s*\(')

    # 类方法调用检测 (receiver 以大写字母开头)
    CLASS_METHOD_PATTERN = re.compile(r'\[\s*([A-Z][A-Za-z0-9]*)\s+\w+')

    # __block self 引用检测
    BLOCK_SELF_PATTERN = re.compile(
        r'__block\s+(?:typeof|__typeof|__typeof__)\s*\(\s*self\s*\)\s*(\w+)\s*=\s*self'
    )

    # 特殊类方法列表：这些类方法会持有 block，使用 self 应报 error 而非 warning
    RETAIN_BLOCK_CLASS_METHODS = re.compile(
        r'\[\s*NSTimer\s+scheduledTimerWithTimeInterval:'
    )

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

            # 检测 __block self 声明（不需要在 block 内，声明本身就是问题）
            block_self_match = self.BLOCK_SELF_PATTERN.search(line)
            if block_self_match:
                related = self.get_related_lines(file_path, line_num, lines)
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=line.find('__block') + 1,
                    lines=lines,
                    violation_type=SubType.BLOCK_SELF,
                    related_lines=related
                ))
                continue

            # 检测 self 使用
            if not self._line_contains_self(line):
                continue

            # 检测 self 的具体使用位置和类型
            self_usages = self._find_self_usages(line)
            if not self_usages:
                continue

            self_usages = [
                (col, usage_type)
                for col, usage_type in self_usages
                if self._is_in_block_at_position(lines, line_num, col)
            ]
            if not self_usages:
                continue

            # 获取当前方法的作用域
            method_start = self._find_method_start(lines, line_num)

            # 在方法作用域内查找 weak/strong 声明
            weak_decls = self._find_weak_declarations(lines, method_start, line_num)
            strong_decls = self._find_strong_declarations(lines, method_start, line_num)

            # 获取 related_lines
            related_lines = self.get_related_lines(file_path, line_num, lines)

            # 检测混用 warning
            if self._has_mixed_usage(weak_decls):
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=1,
                    lines=lines,
                    violation_type=SubType.MIXED_WEAK_STYLE,
                    related_lines=related_lines
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
                    line=line,
                    lines=lines,
                    related_lines=related_lines
                )
                if violation:
                    violations.append(violation)

        return violations

    def _line_contains_self(self, line: str) -> bool:
        """检查行是否包含 self（排除注释和字符串中的）"""
        line_lower = strip_line_comment(line).lower()
        if 'self' not in line_lower:
            return False
        return True

    def _is_in_block_at_position(self, lines: List[str], line_num: int, column: int) -> bool:
        """检测指定位置是否位于 block 作用域内。"""
        method_start = self._find_method_start(lines, line_num)
        brace_stack = []
        pending_block = False
        block_param_depth = 0

        for i in range(method_start - 1, line_num):
            code_line = strip_line_comment(lines[i])
            scan_limit = len(code_line)
            if i == line_num - 1:
                scan_limit = max(0, min(len(code_line), column - 1))

            in_string = False
            escape_next = False

            for char in code_line[:scan_limit]:
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

                if pending_block:
                    if char.isspace():
                        continue

                    if char == ')' and block_param_depth == 0:
                        pending_block = False
                        continue

                    if char == '(':
                        block_param_depth += 1
                        continue

                    if block_param_depth > 0:
                        if char == ')':
                            block_param_depth = max(0, block_param_depth - 1)
                        continue

                if char == '^':
                    pending_block = True
                    block_param_depth = 0
                    continue

                if char == '{':
                    brace_stack.append(pending_block)
                    pending_block = False
                    block_param_depth = 0
                    continue

                if char == '}':
                    if brace_stack:
                        brace_stack.pop()
                    pending_block = False
                    block_param_depth = 0
                    continue

                if char == ';':
                    pending_block = False
                    block_param_depth = 0

        return any(brace_stack)

    def _find_method_start(self, lines: List[str], line_num: int) -> int:
        """查找当前行所属方法的起始行号"""
        for i in range(line_num - 1, -1, -1):
            if self.METHOD_START_PATTERN.match(lines[i].strip()):
                return i + 1  # 返回 1-based 行号
        return 1  # 如果找不到，返回文件开头

    def _strip_comment(self, line: str) -> str:
        """移除行尾注释"""
        return strip_line_comment(line)

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
        返回: 'c_function' | 'class_method' | 'retain_class_method' | 'instance_method'

        策略：找到包含 block 开始 (^{) 的那一行，分析该行的调用上下文。
        如果当前 block 是多 block 参数调用的后续 block（如 completion:^{...}），
        则继续向上搜索整个方法调用的上下文。

        retain_class_method: 类方法会持有 block（如 NSTimer），应升级为 error
        """
        method_start = self._find_method_start(lines, line_num)

        # 先找到 block 开始的行
        block_start_line = None
        block_start_idx = -1

        for i in range(line_num - 2, method_start - 2, -1):
            if i < 0:
                break
            line = lines[i]

            # 如果遇到方法定义，停止搜索
            if self.METHOD_START_PATTERN.match(line.strip()):
                break

            # 找到 block 开始的行
            if self.BLOCK_START_PATTERN.search(line):
                block_start_line = line
                block_start_idx = i
                break

        if block_start_line is None:
            return 'instance_method'

        # 只分析 block 开始那一行的调用上下文
        # 检测 C 函数
        if self.C_FUNCTION_PATTERN.search(block_start_line):
            return 'c_function'

        # 检测类方法调用：[ClassName methodName:^{...}]
        # 类方法调用必须在 block 开始之前
        # 排除嵌套调用模式：[[ClassName xxx] instanceMethod:^{...}]
        block_match = self.BLOCK_START_PATTERN.search(block_start_line)
        if block_match:
            line_before_block = block_start_line[:block_match.start()]
            class_match = self.CLASS_METHOD_PATTERN.search(line_before_block)
            if class_match:
                # 检查是否为嵌套调用：[[ClassName xxx] instanceMethod:]
                # CLASS_METHOD_PATTERN 匹配的 [ 是内层的，如果它前面紧邻另一个 [
                # 则说明是 [[ClassName method] instanceMethod:] 模式
                prefix = line_before_block[:class_match.start()].rstrip()
                if prefix.endswith('['):
                    return 'instance_method'
                # 检查是否为会持有 block 的类方法（如 NSTimer）
                if self.RETAIN_BLOCK_CLASS_METHODS.search(block_start_line):
                    return 'retain_class_method'
                return 'class_method'

            # 如果当前 block 开始行是 "} xxx:^..." 模式（多 block 参数的后续 block），
            # 则继续向上搜索整个方法调用的首个 block 来判断上下文
            stripped_before = line_before_block.strip()
            if stripped_before.startswith('}'):
                # 向上继续查找前一个 block 或方法调用起始行
                for j in range(block_start_idx - 1, method_start - 2, -1):
                    if j < 0:
                        break
                    prev_line = lines[j]
                    if self.METHOD_START_PATTERN.match(prev_line.strip()):
                        break
                    if self.C_FUNCTION_PATTERN.search(prev_line):
                        return 'c_function'
                    prev_class_match = self.CLASS_METHOD_PATTERN.search(prev_line)
                    if prev_class_match:
                        prev_prefix = prev_line[:prev_class_match.start()].rstrip()
                        if prev_prefix.endswith('[[') or prev_prefix.endswith('[ ['):
                            return 'instance_method'
                        if self.RETAIN_BLOCK_CLASS_METHODS.search(prev_line):
                            return 'retain_class_method'
                        return 'class_method'

        return 'instance_method'

    # 字符串字面量匹配（@"..." 或 "..."，支持转义引号）
    STRING_LITERAL_PATTERN = re.compile(r'@?"(?:[^"\\]|\\.)*"')

    def _strip_string_literals(self, line: str) -> str:
        """移除字符串字面量内容，保留位置占位（避免列号偏移影响后续匹配）"""
        def _replace_with_spaces(m):
            return ' ' * len(m.group(0))
        return self.STRING_LITERAL_PATTERN.sub(_replace_with_spaces, line)

    def _find_self_usages(self, line: str) -> List[Tuple[int, str]]:
        """
        查找行中所有 self 使用
        返回: [(column, usage_type), ...]
        usage_type: 'self' | 'weak_var' | 'strong_var' | 'self_weak_'
        """
        usages = []

        # 跳过注释部分
        check_line = strip_line_comment(line)

        # 移除字符串字面量中的内容（避免 @"self" 被误检）
        check_line = self._strip_string_literals(check_line)

        # 跳过 weak/strong 声明行（manual 和 macro）
        if (self.WEAK_MANUAL_PATTERN.search(check_line) or self.STRONG_MANUAL_PATTERN.search(check_line)
                or self.WEAK_MACRO_PATTERN.search(check_line) or self.STRONG_MACRO_PATTERN.search(check_line)):
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

    def _line_has_weak_dereference(self, line: str) -> bool:
        """weak/self_weak_ 只有在被真正解引用时才需要 strongify。"""
        check_line = self._strip_string_literals(strip_line_comment(line))
        return bool(
            re.search(r'\[\s*(?:self_weak_|\w*[sS]elf)\b', check_line) or
            re.search(r'\b(?:self_weak_|\w*[sS]elf)\s*(?:\.|->)', check_line)
        )

    def _check_self_usage(self, file_path: str, line_num: int, column: int,
                          usage_type: str, weak_decls: List[WeakDeclaration],
                          strong_decls: List[StrongDeclaration],
                          block_context: str, line: str,
                          lines: List[str],
                          related_lines: Tuple[int, int]) -> Optional[Violation]:
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

        # 检查是否存在 shadow self（manual 或 macro）
        # shadow self 意味着 self 已被重定义为局部变量，不会导致循环引用
        has_shadow_self = False
        if has_strong:
            manual_strong_name = next((d.var_name for d in strong_decls if not d.is_macro), None)
            if manual_strong_name == 'self' or has_macro_strong:
                has_shadow_self = True

        # 规则 0: C 函数中的 block -> WARNING 或不检测
        if block_context == 'c_function':
            if usage_type == 'self':
                # 如果 self 已被 shadow，则安全
                if has_shadow_self:
                    return None
                return self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=column,
                    lines=lines,
                    violation_type=SubType.C_FUNCTION_SELF,
                    related_lines=related_lines
                )
            return None  # 其他情况 OK

        # 规则 1a: 会持有 block 的类方法（如 NSTimer）-> ERROR
        if block_context == 'retain_class_method':
            if usage_type == 'self':
                if has_shadow_self:
                    return None
                return self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=column,
                    lines=lines,
                    violation_type=SubType.TIMER_BLOCK_SELF,
                    related_lines=related_lines
                )
            return None

        # 规则 1b: 一般类方法调用中的 block -> WARNING
        if block_context == 'class_method':
            # 类方法对 block 的持有语义未知，但直接使用 self 仍然值得提醒。
            if usage_type == 'self' and not has_shadow_self:
                return self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=column,
                    lines=lines,
                    violation_type=SubType.CLASS_METHOD_SELF,
                    related_lines=related_lines
                )
            return None

        # 以下为实例方法中的检测

        # 规则 2: 无 weak 转换 -> ERROR
        if not has_weak:
            if usage_type == 'self':
                return self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=column,
                    lines=lines,
                    violation_type=SubType.DIRECT_SELF,
                    related_lines=related_lines
                )

        # 规则 3: 使用 manual weak 方式
        if has_manual_weak:
            weak_var_name = next((d.var_name for d in weak_decls if not d.is_macro), None)
            strong_var_name = next((d.var_name for d in strong_decls if not d.is_macro), None)

            if usage_type == 'self':
                # 如果 strong 声明的变量名就是 self（如 __strong typeof(weakSelf) self = weakSelf），
                # 则 self 已被 shadow 为 block 内的局部变量，等价于 @strongify(self) -> OK
                if has_strong and strong_var_name == 'self':
                    return None

                # 如果同时有 @strongify(self) 宏，self 也已被 shadow -> OK
                if has_macro_strong:
                    return None

                # 有 weak 但使用了 self -> ERROR
                if has_strong:
                    return self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=column,
                        lines=lines,
                        violation_type=SubType.HAS_STRONG_USE_SELF,
                        related_lines=related_lines,
                        message_vars={"var": strong_var_name or "strongSelf"}
                    )
                else:
                    return self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=column,
                        lines=lines,
                        violation_type=SubType.HAS_WEAK_USE_SELF,
                        related_lines=related_lines,
                        message_vars={"var": weak_var_name or "weakSelf"}
                    )

            elif usage_type == 'weak_var':
                if not self._line_has_weak_dereference(line):
                    return None
                # 使用 weak 变量
                if has_strong:
                    # 有 strong 但用了 weak -> WARNING
                    return self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=column,
                        lines=lines,
                        violation_type=SubType.HAS_STRONG_USE_WEAK,
                        related_lines=related_lines,
                        message_vars={"var": strong_var_name or "strongSelf"}
                    )
                else:
                    # 无 strong，用 weak -> WARNING
                    return self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=column,
                        lines=lines,
                        violation_type=SubType.WEAK_WITHOUT_STRONG,
                        related_lines=related_lines
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
                    return self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=column,
                        lines=lines,
                        violation_type=SubType.NEED_STRONGIFY,
                        related_lines=related_lines
                    )

            elif usage_type == 'self_weak_':
                if not self._line_has_weak_dereference(line):
                    return None
                # 使用 self_weak_ -> WARNING (建议用 @strongify)
                return self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=column,
                    lines=lines,
                    violation_type=SubType.SELF_WEAK_USAGE,
                    related_lines=related_lines
                )

        return None

    def get_related_lines(self, file_path: str, line: int, lines: List[str]) -> Tuple[int, int]:
        """
        获取 Block 所在方法的范围

        审查范围是整个方法，因为需要检查 weak/strong 声明
        """
        method_start = self._find_method_start(lines, line)
        return get_method_range(lines, method_start)
