"""
Reporter Module - 输出格式化 (Xcode 兼容)
"""
import json
import sys
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Set, Tuple
from pathlib import Path

from .logger import get_logger


class Severity(Enum):
    """严重级别"""
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"


@dataclass
class Violation:
    """违规记录"""
    file_path: str
    line: int
    column: int
    severity: Severity
    message: str
    rule_id: str
    source: str = "biliobjclint"  # biliobjclint | oclint
    pod_name: Optional[str] = None  # 所属本地 Pod 名称（None 表示主工程）
    related_lines: Optional[Tuple[int, int]] = None  # 关联行范围 (start, end)，用于增量过滤

    def to_xcode_format(self) -> str:
        """
        转换为 Xcode 可识别的格式
        格式: /path/to/file.m:line:column: warning: message [rule_id]
        """
        severity_str = self.severity.value
        return f"{self.file_path}:{self.line}:{self.column}: {severity_str}: {self.message} [{self.rule_id}]"

    def to_dict(self) -> dict:
        """转换为字典"""
        result = {
            "file": self.file_path,
            "line": self.line,
            "column": self.column,
            "severity": self.severity.value,
            "message": self.message,
            "rule": self.rule_id,
            "source": self.source
        }
        if self.pod_name:
            result["pod_name"] = self.pod_name
        return result


class Reporter:
    """报告生成器"""

    def __init__(self, xcode_output: bool = True):
        self.violations: List[Violation] = []
        self.xcode_output = xcode_output
        self.logger = get_logger("biliobjclint")

    def add_violation(self, violation: Violation):
        """添加违规记录"""
        self.violations.append(violation)
        self.logger.debug(f"Added violation: {violation.rule_id} at {violation.file_path}:{violation.line}")

    def add_violations(self, violations: List[Violation]):
        """批量添加违规记录"""
        self.violations.extend(violations)

    def filter_by_changed_lines(self, changed_lines_map: dict):
        """
        根据变更行号过滤违规

        Args:
            changed_lines_map: {file_path: {line_numbers}}
        """
        if not changed_lines_map:
            self.logger.debug("No changed lines map provided, skipping filter")
            return

        before_count = len(self.violations)
        filtered = []
        for v in self.violations:
            if v.file_path in changed_lines_map:
                changed_lines = changed_lines_map[v.file_path]
                # 如果没有指定变更行（新文件），保留所有
                if not changed_lines:
                    filtered.append(v)
                elif v.line in changed_lines:
                    filtered.append(v)
                elif v.related_lines:
                    # 检查关联行范围是否与变更行有交集
                    start, end = v.related_lines
                    if any(line in changed_lines for line in range(start, end + 1)):
                        filtered.append(v)
            # 如果文件不在变更列表中，丢弃

        self.violations = filtered
        self.logger.debug(f"Filtered violations by changed lines: {before_count} -> {len(self.violations)}")

    def deduplicate(self):
        """去重：相同位置的违规只保留一个"""
        seen = set()
        unique = []
        for v in self.violations:
            key = (v.file_path, v.line, v.column, v.rule_id)
            if key not in seen:
                seen.add(key)
                unique.append(v)
        self.violations = unique

    def sort(self):
        """按文件和行号排序"""
        self.violations.sort(key=lambda v: (v.file_path, v.line, v.column))

    def report(self) -> int:
        """
        输出报告

        Returns:
            返回码：有 error 返回 1，否则返回 0
        """
        self.deduplicate()
        self.sort()

        has_error = False

        for v in self.violations:
            if self.xcode_output:
                print(v.to_xcode_format())
            else:
                print(f"[{v.severity.value.upper()}] {v.file_path}:{v.line}:{v.column} - {v.message} ({v.rule_id})")

            if v.severity == Severity.ERROR:
                has_error = True

        return 1 if has_error else 0

    def get_display_path(self, violation: Violation) -> str:
        """
        获取用于显示的文件路径（带 Pod 名称前缀）

        用于 HTML 报告和日志输出
        """
        if violation.pod_name:
            # 对于本地 Pod，显示 [PodName] 前缀 + 相对路径
            try:
                from pathlib import Path
                file_path = Path(violation.file_path)
                # 只取文件名或最后两级路径
                if len(file_path.parts) > 2:
                    rel_display = "/".join(file_path.parts[-2:])
                else:
                    rel_display = file_path.name
                return f"[{violation.pod_name}] {rel_display}"
            except Exception:
                return f"[{violation.pod_name}] {violation.file_path}"
        return violation.file_path

    def get_summary(self) -> dict:
        """获取统计摘要"""
        error_count = sum(1 for v in self.violations if v.severity == Severity.ERROR)
        warning_count = sum(1 for v in self.violations if v.severity == Severity.WARNING)

        return {
            "total": len(self.violations),
            "errors": error_count,
            "warnings": warning_count,
            "files_affected": len(set(v.file_path for v in self.violations))
        }

    def to_json(self) -> str:
        """输出 JSON 格式报告"""
        return json.dumps({
            "summary": self.get_summary(),
            "violations": [v.to_dict() for v in self.violations]
        }, indent=2, ensure_ascii=False)

    def print_summary(self):
        """打印摘要到 stderr（不影响 Xcode 解析）"""
        summary = self.get_summary()
        print(f"\n{'='*50}", file=sys.stderr)
        print(f"BiliObjCLint Summary:", file=sys.stderr)
        print(f"  Total violations: {summary['total']}", file=sys.stderr)
        print(f"  Errors: {summary['errors']}", file=sys.stderr)
        print(f"  Warnings: {summary['warnings']}", file=sys.stderr)
        print(f"  Files affected: {summary['files_affected']}", file=sys.stderr)
        print(f"{'='*50}\n", file=sys.stderr)
