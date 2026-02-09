# Custom Rules Development

本文档介绍如何为 BiliObjCLint 开发自定义规则。

## Python 规则（推荐）

Python 规则开发简单，无需重新编译，适合大多数场景。

### 创建规则

在 `custom_rules/python/` 目录下创建 `.py` 文件：

```python
from core.lint.rules.base_rule import BaseRule
from core.lint.reporter import ViolationType, Severity

class MyCustomRule(BaseRule):
    # 规则标识符（必须唯一）
    identifier = "my_custom_rule"

    # 规则名称
    name = "My Custom Rule"

    # 规则中文显示名称
    display_name = "自定义规则"

    # 规则描述
    description = "检查自定义模式"

    # 默认严重级别: warning | error
    default_severity = "warning"

    # 定义 ViolationType（sub_type + message + severity 绑定）
    class SubType:
        BAD_PATTERN = ViolationType("bad_pattern", "发现不良模式: {desc}")
        CRITICAL_ISSUE = ViolationType("critical_issue", "发现严重问题", Severity.ERROR)

    def check(self, file_path, content, lines, changed_lines):
        """
        执行规则检查

        Args:
            file_path: 文件路径
            content: 文件完整内容
            lines: 文件按行分割的列表
            changed_lines: 变更的行号集合（空集合表示检查全部）

        Returns:
            违规列表
        """
        violations = []

        for line_num, line in enumerate(lines, 1):
            # 增量模式下只检查变更的行
            if not self.should_check_line(line_num, changed_lines):
                continue

            # 你的检查逻辑
            if "bad_pattern" in line:
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=1,
                    lines=lines,
                    violation_type=self.SubType.BAD_PATTERN,
                    message_vars={"desc": line.strip()}  # 可选：替换消息中的变量
                ))

        return violations
```

### 规则配置

在 `.biliobjclint/config.yaml` 中配置自定义规则：

```yaml
python_rules:
  my_custom_rule:
    enabled: true
    severity: warning
    params:
      # 自定义参数
      max_length: 100
```

### 获取配置参数

```python
def check(self, file_path, content, lines, changed_lines):
    # 获取配置参数
    max_length = self.get_param("max_length", 100)

    # 使用参数...
```

### 示例：检查硬编码字符串

```python
import re
from core.lint.rules.base_rule import BaseRule
from core.lint.reporter import ViolationType

class HardcodedStringRule(BaseRule):
    identifier = "hardcoded_string"
    name = "Hardcoded String Check"
    display_name = "硬编码字符串"
    description = "检查硬编码的中文字符串"
    default_severity = "warning"

    class SubType:
        CHINESE_STRING = ViolationType("chinese_string", "发现硬编码中文字符串: {text}")

    def check(self, file_path, content, lines, changed_lines):
        violations = []

        # 匹配 @"包含中文的字符串"
        pattern = re.compile(r'@"[^"]*[\u4e00-\u9fa5][^"]*"')

        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue

            matches = pattern.finditer(line)
            for match in matches:
                violations.append(self.create_violation(
                    file_path=file_path,
                    line=line_num,
                    column=match.start() + 1,
                    lines=lines,
                    violation_type=self.SubType.CHINESE_STRING,
                    message_vars={"text": match.group()}
                ))

        return violations
```

## 规则最佳实践

1. **明确的规则 ID**: 使用 `snake_case` 命名，确保唯一
2. **清晰的错误信息**: 说明问题是什么以及如何修复
3. **支持增量检查**: 使用 `should_check_line()` 过滤未变更的行
4. **合理的严重级别**:
   - `error`: 必须修复的问题
   - `warning`: 建议修复的问题
5. **可配置**: 使用参数让规则更灵活

## 调试规则

```bash
# 详细输出模式
.venv/bin/python3 scripts/biliobjclint.py \
    --files tests/TestFile.m \
    --verbose
```

查看日志：
```bash
tail -f logs/biliobjclint_*.log
```
