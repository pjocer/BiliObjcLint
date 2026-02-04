"""
Violation Hash Module - 违规代码内容哈希计算

用于 Metrics 上报去重：相同文件 + 相同 violations + 相同代码内容 = 重复数据
"""
import hashlib
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .reporter import Violation
    from .rules.base_rule import BaseRule


def calculate_violation_hash(
    violation: 'Violation',
    rule: 'BaseRule',
    lines: List[str],
) -> Optional[str]:
    """
    计算 violation 的代码内容哈希

    不同规则使用不同的哈希策略：
    - 单行规则：仅哈希违规所在行
    - Block 范围规则：哈希整个 Block
    - 方法范围规则：哈希整个方法
    - 文件头规则：哈希前 N 行

    Args:
        violation: 违规对象
        rule: 对应的规则实例（用于调用 get_hash_context）
        lines: 文件内容行列表

    Returns:
        MD5 哈希字符串（16 字符），如果无法计算则返回 None
    """
    if not lines:
        return None

    try:
        # 调用规则的 get_hash_context() 获取哈希范围
        start, end = rule.get_hash_context(
            violation.file_path,
            violation.line,
            lines,
            violation
        )

        return compute_hash_from_range(violation.rule_id, lines, start, end)

    except Exception:
        # 计算失败时返回 None，不影响主流程
        return None


def compute_hash_from_range(
    rule_id: str,
    lines: List[str],
    start: int,
    end: int,
) -> Optional[str]:
    """
    从代码范围计算哈希值

    Args:
        rule_id: 规则 ID
        lines: 文件内容行列表
        start: 开始行号（1-indexed, inclusive）
        end: 结束行号（1-indexed, inclusive）

    Returns:
        MD5 哈希字符串（16 字符），如果无法计算则返回 None
    """
    try:
        # 边界检查
        start = max(1, start)
        end = min(len(lines), end)

        if start > end:
            return None

        # 提取代码上下文并归一化（去除空白差异）
        context = lines[start - 1:end]  # 转为 0-indexed
        normalized = ''.join(line.strip() for line in context)

        # 构建哈希输入：rule_id + 归一化代码
        hash_input = f"{rule_id}:{normalized}"

        # 计算 MD5 并截取前 16 字符
        return hashlib.md5(hash_input.encode()).hexdigest()[:16]

    except Exception:
        return None
