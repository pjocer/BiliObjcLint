"""
Reporter Module - 输出格式化 (Xcode 兼容)
"""
import hashlib
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set, Tuple, NamedTuple
from pathlib import Path

from lib.logger import get_logger


class Severity(Enum):
    """严重级别"""
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"


class ViolationType(NamedTuple):
    """
    违规类型定义（sub_type + message + severity 绑定）

    用于在规则中定义 SubType，将 sub_type、message、severity 统一管理。

    Attributes:
        id: sub_type 标识（稳定，用于系统匹配/去重）
        message: 用户可读描述（可包含 {var} 占位符）
        severity: 违规级别，默认 WARNING
    """
    id: str
    message: str
    severity: Severity = Severity.WARNING


@dataclass
class Violation:
    """违规记录"""
    file_path: str
    line: int
    column: int
    severity: Severity
    message: str
    rule_id: str
    source: str = "biliobjclint"
    pod_name: Optional[str] = None  # 所属本地 Pod 名称（None 表示主工程）
    related_lines: Optional[Tuple[int, int]] = None  # 关联行范围 (start, end)，用于增量过滤
    context: Optional[str] = None  # 关联行的代码内容
    code_hash: Optional[str] = None  # 代码内容哈希（纯代码内容，不含 rule_id）
    sub_type: Optional[str] = None  # 规则子类型（稳定标识，用于区分同一规则的不同违规类型）
    rule_name: Optional[str] = None  # 规则中文名称（用于 UI 显示，如"禁用 API"）
    _violation_id: Optional[str] = field(default=None, repr=False)  # 缓存的 violation_id

    @property
    def violation_id(self) -> str:
        """
        获取违规唯一标识（懒计算，缓存结果）

        组成：hash(file_path + rule_id + sub_type + code_hash + line_offset + column)
        """
        if self._violation_id is None:
            self._violation_id = self._compute_violation_id()
        return self._violation_id

    def _compute_violation_id(self) -> str:
        """
        计算违规唯一标识

        组成元素：
        - file_path: 文件路径
        - rule_id: 规则标识
        - sub_type: 规则子类型（稳定标识）
        - code_hash: context 的 hash（纯代码内容）
        - line_offset: 相对行号（对代码块外部变化免疫）
        - column: 列号
        """
        line_offset = self.line - self.related_lines[0] if self.related_lines else 0
        sub_type = self.sub_type or "default"
        code_hash = self.code_hash or ""

        id_input = f"{self.file_path}:{self.rule_id}:{sub_type}:{code_hash}:{line_offset}:{self.column}"
        return hashlib.md5(id_input.encode()).hexdigest()[:16]

    def to_xcode_format(self) -> str:
        """
        转换为 Xcode 可识别的格式
        格式: /path/to/file.m:line:column: warning: message [rule_id]
        """
        severity_str = self.severity.value
        return f"{self.file_path}:{self.line}:{self.column}: {severity_str}: {self.message} [{self.rule_id}]"

    def to_dict(self) -> dict:
        """
        唯一序列化入口

        Returns:
            包含所有非空字段的字典
        """
        result = {
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "severity": self.severity.value,
            "message": self.message,
            "rule_id": self.rule_id,
            "source": self.source,
            "violation_id": self.violation_id  # 始终包含（唯一标识）
        }
        if self.pod_name:
            result["pod_name"] = self.pod_name
        if self.related_lines:
            result["related_lines"] = list(self.related_lines)
        if self.context:
            result["context"] = self.context
        if self.code_hash:
            result["code_hash"] = self.code_hash
        if self.sub_type:
            result["sub_type"] = self.sub_type
        if self.rule_name:
            result["rule_name"] = self.rule_name
        return result

    @classmethod
    def from_dict(cls, d: dict) -> 'Violation':
        """
        唯一反序列化入口（兼容旧格式）

        Args:
            d: 字典数据，支持旧格式 (file/rule) 和新格式 (file_path/rule_id)

        Returns:
            Violation 对象
        """
        return cls(
            file_path=d.get("file_path") or d.get("file", ""),
            line=d.get("line", 0),
            column=d.get("column", 0),
            severity=Severity(d.get("severity", "warning")),
            message=d.get("message", ""),
            rule_id=d.get("rule_id") or d.get("rule", ""),
            source=d.get("source", "biliobjclint"),
            pod_name=d.get("pod_name"),
            related_lines=tuple(d["related_lines"]) if d.get("related_lines") else None,
            context=d.get("context"),
            code_hash=d.get("code_hash"),
            sub_type=d.get("sub_type"),
            rule_name=d.get("rule_name"),
        )


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

    def to_json_dict(self, run_id: Optional[str] = None, extra: Optional[dict] = None) -> dict:
        """输出 JSON 数据结构"""
        data = {
            "summary": self.get_summary(),
            "violations": [v.to_dict() for v in self.violations]
        }
        if run_id:
            data["run_id"] = run_id
        if extra:
            data.update(extra)
        return data

    def to_json(self, run_id: Optional[str] = None, extra: Optional[dict] = None) -> str:
        """输出 JSON 格式报告"""
        return json.dumps(self.to_json_dict(run_id=run_id, extra=extra), indent=2, ensure_ascii=False)

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
