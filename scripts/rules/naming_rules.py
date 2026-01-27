"""
Naming Rules - 命名规范规则
"""
import re
from typing import List, Set

from .base_rule import BaseRule
from core.reporter import Violation


class ClassPrefixRule(BaseRule):
    """类名前缀检查"""

    identifier = "class_prefix"
    name = "Class Prefix Check"
    description = "检查类名是否使用指定前缀"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        prefix = self.get_param("prefix", "")
        if not prefix:
            return violations  # 未配置前缀，跳过

        # 匹配 @interface/@implementation 声明
        # @interface ClassName : SuperClass
        # @interface ClassName (Category)
        # @implementation ClassName
        pattern = r'@(?:interface|implementation)\s+([A-Z][A-Za-z0-9_]*)\s*(?:[:(]|$)'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            match = re.search(pattern, line)
            if match:
                class_name = match.group(1)

                # 跳过系统类和常见第三方类前缀
                skip_prefixes = ['NS', 'UI', 'CG', 'CA', 'CF', 'AV', 'MK', 'CL', 'SK', 'SC']
                if any(class_name.startswith(p) for p in skip_prefixes):
                    continue

                # 检查是否使用了指定前缀
                if not class_name.startswith(prefix):
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=match.start(1) + 1,
                        message=f"类名 '{class_name}' 应使用前缀 '{prefix}'"
                    ))

        return violations


class PropertyNamingRule(BaseRule):
    """属性命名检查（小驼峰）"""

    identifier = "property_naming"
    name = "Property Naming Check"
    description = "检查属性命名是否符合小驼峰规范"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 匹配 @property 声明
        # @property (nonatomic, strong) NSString *userName;
        pattern = r'@property\s*\([^)]*\)\s*\w+[\s*]+\*?\s*(\w+)\s*;'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            match = re.search(pattern, line)
            if match:
                prop_name = match.group(1)

                # 检查是否以小写字母开头
                if prop_name and prop_name[0].isupper():
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=match.start(1) + 1,
                        message=f"属性名 '{prop_name}' 应使用小驼峰命名（首字母小写）"
                    ))

                # 检查是否包含下划线（IBOutlet 除外）
                if '_' in prop_name and 'IBOutlet' not in line:
                    violations.append(self.create_violation(
                        file_path=file_path,
                        line=line_num,
                        column=match.start(1) + 1,
                        message=f"属性名 '{prop_name}' 不应包含下划线，请使用小驼峰命名"
                    ))

        return violations


class ConstantNamingRule(BaseRule):
    """常量命名检查"""

    identifier = "constant_naming"
    name = "Constant Naming Check"
    description = "检查常量命名是否符合规范"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 匹配 #define 宏常量（全大写）
        define_pattern = r'#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+'

        # 匹配 const 常量
        const_pattern = r'(?:static\s+)?(?:const\s+)?\w+\s*\*?\s*(?:const\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*='

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 检查 #define
            match = re.search(define_pattern, line)
            if match:
                const_name = match.group(1)

                # 跳过函数宏
                if '(' in line[match.end():match.end()+1]:
                    continue

                # 跳过小写字母开头的宏（通常是函数式宏或特殊用途）
                if const_name[0].islower():
                    continue

                # 宏常量应该全大写
                if not const_name.isupper() and not const_name.startswith('k'):
                    # 检查是否是混合大小写
                    if any(c.islower() for c in const_name) and any(c.isupper() for c in const_name):
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=match.start(1) + 1,
                            message=f"宏常量 '{const_name}' 应使用全大写加下划线命名（如 MAX_COUNT）或 k 前缀命名（如 kMaxCount）"
                        ))

        return violations


class MethodNamingRule(BaseRule):
    """方法命名检查"""

    identifier = "method_naming"
    name = "Method Naming Check"
    description = "检查方法命名是否符合小驼峰规范"
    default_severity = "warning"

    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        violations = []

        # 匹配方法声明
        # - (void)doSomething;
        # + (instancetype)sharedInstance;
        pattern = r'^[-+]\s*\([^)]+\)\s*([a-zA-Z_][a-zA-Z0-9_]*)'

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 去除注释
            code_line = line.split('//')[0]

            match = re.search(pattern, code_line)
            if match:
                method_name = match.group(1)

                # 方法名应以小写字母开头
                if method_name and method_name[0].isupper():
                    # 跳过 init 系列方法的特殊情况
                    if not method_name.startswith('init'):
                        violations.append(self.create_violation(
                            file_path=file_path,
                            line=line_num,
                            column=match.start(1) + 1,
                            message=f"方法名 '{method_name}' 应以小写字母开头"
                        ))

        return violations
