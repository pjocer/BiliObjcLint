"""
Block Retain Cycle Rule - Block 循环引用检查
"""
import re
from typing import List, Set, Optional, Tuple
from dataclasses import dataclass

from ..base_rule import BaseRule
from core.reporter import Violation, Severity


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
