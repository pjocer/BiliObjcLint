"""Resolve precise repair ranges that may extend beyond a lint review range."""

import re
from dataclasses import replace
from pathlib import Path
from typing import List, Sequence, Tuple

from auto_fix.models import FixViolation


_METHOD_DECLARATION = re.compile(r"^[-+]\s*\([^)]+\)\s*([A-Za-z_][A-Za-z0-9_]*)")


def _code_only_lines(lines: Sequence[str]) -> List[str]:
    """Blank comments and literals while preserving code positions and line count."""
    result: List[str] = []
    in_block_comment = False
    for line in lines:
        output = list(line)
        index = 0
        while index < len(line):
            if in_block_comment:
                end = line.find("*/", index)
                if end < 0:
                    output[index:] = " " * (len(line) - index)
                    index = len(line)
                    continue
                output[index:end + 2] = " " * (end + 2 - index)
                index = end + 2
                in_block_comment = False
                continue

            if line.startswith("//", index):
                output[index:] = " " * (len(line) - index)
                break
            if line.startswith("/*", index):
                output[index:index + 2] = "  "
                index += 2
                in_block_comment = True
                continue
            if line[index] in {'"', "'"}:
                quote = line[index]
                output[index] = " "
                index += 1
                while index < len(line):
                    output[index] = " "
                    if line[index] == "\\":
                        index += 1
                        if index < len(line):
                            output[index] = " "
                    elif line[index] == quote:
                        index += 1
                        break
                    index += 1
                continue
            index += 1
        result.append("".join(output))
    return result


def resolve_repair_scopes(targets: Sequence[FixViolation]) -> List[FixViolation]:
    """Add exact same-file selector references for supported naming repairs."""
    return [_resolve_method_naming_scope(target) for target in targets]


def validate_repair_postconditions(
    targets: Sequence[FixViolation],
) -> Tuple[bool, str]:
    """Ensure a scoped selector rename updated every discovered code reference."""
    for target in targets:
        if not target.symbol_name:
            continue
        lines = Path(target.file_path).read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
        code_lines = _code_only_lines(lines)
        symbol_pattern = re.compile(rf"\b{re.escape(target.symbol_name)}\b")
        for start, end in target.allowed_ranges:
            for line_number in range(start, end + 1):
                code = code_lines[line_number - 1]
                if symbol_pattern.search(code):
                    return False, f"方法改名仍有未更新的调用点: {target.file_path}:{line_number}"
    return True, "修复范围一致"


def _resolve_method_naming_scope(target: FixViolation) -> FixViolation:
    if target.rule_id != "method_naming" or target.sub_type != "uppercase_start":
        return target

    lines = Path(target.file_path).read_text(encoding="utf-8", errors="replace").splitlines()
    declaration = lines[target.line - 1]
    match = _METHOD_DECLARATION.search(declaration.lstrip())
    if not match:
        return target
    symbol = match.group(1)
    if not symbol or not symbol[0].isupper():
        return target

    symbol_pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    ranges = set(target.allowed_ranges or (target.related_lines,))
    for line_number, code in enumerate(_code_only_lines(lines), 1):
        if symbol_pattern.search(code):
            ranges.add((line_number, line_number))

    replacement_symbol = symbol[0].lower() + symbol[1:]
    return replace(
        target,
        allowed_ranges=tuple(sorted(ranges)),
        symbol_name=symbol,
        replacement_symbol=replacement_symbol,
    )
