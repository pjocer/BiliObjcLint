"""Canonical data models used by the automatic repair pipeline."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class FixViolation:
    """Immutable automatic-repair target created from canonical lint JSON."""

    file_path: str
    line: int
    column: int
    severity: str
    message: str
    rule_id: str
    related_lines: Tuple[int, int]
    context: str
    code_hash: str
    sub_type: Optional[str]
    violation_id: str
    allowed_ranges: Tuple[Tuple[int, int], ...] = ()
    symbol_name: Optional[str] = None
    replacement_symbol: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FixViolation":
        if not isinstance(data, dict):
            raise ValueError("violation must be an object")

        file_value = data.get("file_path")
        if not isinstance(file_value, str) or not file_value.strip():
            raise ValueError("file_path is required; legacy file is not supported")
        rule_id = data.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError("rule_id is required; legacy rule is not supported")

        file_path = Path(file_value).expanduser().resolve()
        if not file_path.is_file():
            raise ValueError(f"file_path does not exist: {file_path}")

        try:
            line = int(data.get("line", 0))
            column = int(data.get("column", 0))
        except (TypeError, ValueError) as error:
            raise ValueError("line and column must be integers") from error
        if line < 1 or column < 0:
            raise ValueError("line must be positive and column must not be negative")

        related = data.get("related_lines")
        if not isinstance(related, (list, tuple)) or len(related) != 2:
            raise ValueError("related_lines must contain start and end")
        try:
            start, end = int(related[0]), int(related[1])
        except (TypeError, ValueError) as error:
            raise ValueError("related_lines must contain integers") from error

        line_count = len(file_path.read_text(encoding="utf-8", errors="replace").splitlines())
        if start < 1 or end < start or not start <= line <= end or end > line_count:
            raise ValueError(
                f"related_lines must be a valid file range containing line {line}: {start}-{end}"
            )

        violation_id = data.get("violation_id")
        if not isinstance(violation_id, str) or not violation_id.strip():
            raise ValueError("violation_id is required")

        return cls(
            file_path=str(file_path),
            line=line,
            column=column,
            severity=str(data.get("severity") or "warning"),
            message=str(data.get("message") or ""),
            rule_id=rule_id,
            related_lines=(start, end),
            context=str(data.get("context") or ""),
            code_hash=str(data.get("code_hash") or ""),
            sub_type=str(data["sub_type"]) if data.get("sub_type") else None,
            violation_id=violation_id,
            allowed_ranges=((start, end),),
        )

    def to_prompt_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "message": self.message,
            "rule_id": self.rule_id,
            "sub_type": self.sub_type,
            "violation_id": self.violation_id,
            "related_lines": list(self.related_lines),
            "code_hash": self.code_hash,
            "suggested_symbol_replacement": (
                {
                    "from": self.symbol_name,
                    "to": self.replacement_symbol,
                }
                if self.symbol_name and self.replacement_symbol
                else None
            ),
        }


def normalize_violations(
    items: Sequence[Dict[str, Any]],
) -> Tuple[List[FixViolation], List[str]]:
    targets: List[FixViolation] = []
    errors: List[str] = []
    for index, item in enumerate(items):
        try:
            targets.append(FixViolation.from_dict(item))
        except ValueError as error:
            errors.append(f"violation[{index}]: {error}")
    return targets, errors
