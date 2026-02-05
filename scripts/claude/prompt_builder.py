"""
Claude Fixer - Prompt 构建模块

负责构建发送给 Claude 的修复提示词
"""
from typing import Dict, List, Optional, Tuple


def _read_file_lines(file_path: str) -> Optional[List[str]]:
    """读取文件内容"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.readlines()
    except Exception:
        return None


def _extract_code_context(lines: List[str], related_lines: Tuple[int, int], violation_line: int) -> str:
    """
    提取代码上下文

    Args:
        lines: 文件所有行
        related_lines: (start, end) 1-indexed
        violation_line: 违规行号

    Returns:
        带行号的代码块字符串
    """
    start, end = related_lines
    # 转换为 0-indexed
    start_idx = max(0, start - 1)
    end_idx = min(len(lines), end)

    code_parts = []
    for i in range(start_idx, end_idx):
        line_num = i + 1
        line_content = lines[i].rstrip('\n\r')
        # 标记违规行
        marker = " <<<" if line_num == violation_line else ""
        code_parts.append(f"{line_num:4d} | {line_content}{marker}")

    return '\n'.join(code_parts)


def build_fix_prompt(violations: List[Dict]) -> str:
    """
    构建修复 prompt

    Args:
        violations: 违规列表

    Returns:
        发送给 Claude 的 prompt
    """
    # 按文件分组
    by_file = {}
    for v in violations:
        file_path = v.get('file', '')
        if file_path not in by_file:
            by_file[file_path] = []
        by_file[file_path].append(v)

    prompt_parts = [
        "# 代码修复任务（最小化修改）",
        "",
        "## ⚠️ 严格限制 - 必须遵守",
        "",
        "**你的任务是做最小限度的修改来修复指定问题。**",
        "",
        "### 禁止行为（违反将导致任务失败）：",
        "- ❌ 禁止重构代码",
        "- ❌ 禁止优化代码",
        "- ❌ 禁止重写代码",
        "- ❌ 禁止改变代码结构",
        "- ❌ 禁止修改未列出的代码行",
        "- ❌ 禁止添加新功能",
        "- ❌ 禁止删除未涉及的代码",
        "- ❌ 禁止修改代码风格或格式",
        "- ❌ 禁止添加注释或文档",
        "- ❌ 禁止修复未在下方列表中明确指出的问题",
        "",
        "### 允许行为：",
        "- ✅ 只修改下方列表中指定行号的代码",
        "- ✅ 做最小限度的字符级别修改",
        "- ✅ 例如：将 `strong` 改为 `weak`，仅此而已",
        "",
        "## 需要修复的问题（仅修复这些）",
        ""
    ]

    for file_path, file_violations in by_file.items():
        prompt_parts.append(f"### 文件: {file_path}")
        prompt_parts.append("")

        # 预读取文件内容
        file_lines = _read_file_lines(file_path)

        for v in file_violations:
            line = v.get('line', 0)
            message = v.get('message', '')
            rule = v.get('rule', '')
            related_lines = v.get('related_lines')

            prompt_parts.append(f"- **行 {line}**: {message} [{rule}]")

            # 如果有 related_lines 和文件内容，展示代码上下文
            if related_lines and file_lines:
                code_context = _extract_code_context(file_lines, related_lines, line)
                prompt_parts.append("")
                prompt_parts.append("  ```objc")
                for code_line in code_context.split('\n'):
                    prompt_parts.append(f"  {code_line}")
                prompt_parts.append("  ```")
                prompt_parts.append("")

        prompt_parts.append("")

    prompt_parts.extend([
        "## 修复方法参考",
        "",
        "| 规则 | 修复方法 | 示例 |",
        "|------|----------|------|",
        "| weak_delegate | 将 `strong` 改为 `weak` | `@property (nonatomic, strong)` → `@property (nonatomic, weak)` |",
        "| property_naming | 将首字母改为小写 | `URL` → `url` |",
        "| constant_naming | 添加 `k` 前缀 | `Constant` → `kConstant` |",
        "",
        "## 执行指令",
        "",
        "1. 读取文件，定位到指定行号",
        "2. 仅修改该行中与问题相关的最小部分",
        "3. 使用 Edit 工具提交修改",
        "4. 不要做任何额外的修改",
        "",
        "**再次强调：只做最小修改，不要重写或优化任何代码！**"
    ])

    return "\n".join(prompt_parts)
