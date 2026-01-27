"""
Memory Rules - 内存相关规则
"""
import re
from typing import List, Set

from .base_rule import BaseRule
from core.reporter import Violation


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


class BlockRetainCycleRule(BaseRule):
    """Block 循环引用检查"""

    identifier = "block_retain_cycle"
    name = "Block Retain Cycle Check"
    description = "检测 Block 中可能的循环引用"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 检测模式：在 block 内部直接使用 self
        # 这是一个简化的检测，可能有误报
        in_block = False
        block_start_line = 0
        brace_count = 0

        # 检查是否有 weakSelf 或 strongSelf 声明
        weak_self_pattern = r'__weak\s+(?:typeof\(self\)|__typeof\(self\)|__typeof__\(self\)|id)\s*\w*[wW]eak[sS]elf\s*='
        strong_self_pattern = r'__strong\s+(?:typeof\(\w+\)|__typeof\(\w+\)|__typeof__\(\w+\)|id)\s*\w*[sS]trong[sS]elf\s*='

        has_weak_self = bool(re.search(weak_self_pattern, content))

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 检测 block 开始：^{ 或 ^(参数)
            if re.search(r'\^\s*[\({]', line):
                in_block = True
                block_start_line = line_num
                brace_count = 0

            if in_block:
                brace_count += line.count('{') - line.count('}')

                # 检测 block 内使用 self 且没有 weakSelf
                # 跳过 weakSelf/strongSelf 声明行
                if 'self' in line:
                    # 排除 weakSelf/strongSelf 声明
                    if not re.search(weak_self_pattern, line) and not re.search(strong_self_pattern, line):
                        # 检测直接使用 self（包括 self.xxx, [self xxx], self->xxx）
                        direct_self_pattern = r'(?<!\w)self(?:\.|->|\s*\]|\s+\w)'

                        if re.search(direct_self_pattern, line):
                            # 检查上下文中是否有 weakSelf
                            # 查找当前方法范围内的 weakSelf 声明
                            context_start = max(0, line_num - 50)
                            context = '\n'.join(lines[context_start:line_num])

                            if not re.search(weak_self_pattern, context):
                                violations.append(self.create_violation(
                                    file_path=file_path,
                                    line=line_num,
                                    column=line.find('self') + 1,
                                    message="Block 内直接使用 self 可能导致循环引用，建议使用 weakSelf"
                                ))

                # block 结束
                if brace_count <= 0:
                    in_block = False

        return violations


class StrongSelfInBlockRule(BaseRule):
    """Block 内使用 strongSelf 检查"""

    identifier = "strong_self_in_block"
    name = "Strong Self in Block Check"
    description = "检查 Block 内使用 weakSelf 后是否正确使用 strongSelf"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 检测是否在 block 内使用了 weakSelf 但没有转换为 strongSelf
        weak_self_pattern = r'__weak\s+(?:typeof\(self\)|__typeof\(self\)|id)\s*(\w*[wW]eak[sS]elf)\s*='
        strong_self_pattern = r'__strong\s+(?:typeof\(\w+\)|__typeof\(\w+\)|id)\s*\w*[sS]trong[sS]elf\s*='

        # 寻找 weakSelf 声明
        for match in re.finditer(weak_self_pattern, content):
            weak_self_var = match.group(1)

            # 找到使用 weakSelf 的位置
            weak_self_usage = re.search(rf'\b{weak_self_var}\b', content[match.end():])

            if weak_self_usage:
                # 检查附近是否有 strongSelf 声明
                usage_pos = match.end() + weak_self_usage.start()
                context_after = content[usage_pos:usage_pos + 500]

                # 如果使用了 weakSelf 但没有 strongSelf，给出提示
                if not re.search(strong_self_pattern, context_after):
                    # 计算行号
                    line_num = content[:usage_pos].count('\n') + 1

                    if not changed_lines or line_num in changed_lines:
                        pass  # 这个检查可能有太多误报，暂时禁用
                        # violations.append(self.create_violation(
                        #     file_path=file_path,
                        #     line=line_num,
                        #     column=1,
                        #     message=f"使用 {weak_self_var} 时建议先转换为 strongSelf 并检查是否为 nil"
                        # ))

        return violations
