"""Shared UI components for BiliObjCLint server."""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

# Rule ID to Chinese name mapping
RULE_NAMES = {
    # Memory rules
    "block_retain_cycle": "循环引用",
    "collection_mutation": "集合变异",
    "dict_usage": "字典访问",
    "weak_delegate": "弱引用代理",
    "wrapper_empty_pointer": "空指针检查",
    # Naming rules
    "class_prefix": "类名前缀",
    "constant_naming": "常量命名",
    "method_naming": "方法命名",
    "method_parameter": "参数命名",
    "property_naming": "属性命名",
    # Security rules
    "forbidden_api": "禁用 API",
    "hardcoded_credentials": "硬编码凭证",
    "insecure_random": "不安全随机数",
    # Style rules
    "file_header": "文件头注释",
    "line_length": "行长度",
    "method_length": "方法长度",
    "todo_fixme": "待办事项",
}


def get_rule_display_name(rule_id: str) -> str:
    """Get Chinese display name for a rule ID."""
    return RULE_NAMES.get(rule_id, rule_id)


def render_ios_switch(enabled: bool) -> str:
    """Render an iOS-style toggle switch (read-only)."""
    on_class = "on" if enabled else ""
    return f'<span class="ios-switch {on_class}"><span class="slider"></span></span>'


def render_rule_name(rule_id: str) -> str:
    """Render rule name with Chinese display and English tooltip."""
    display_name = get_rule_display_name(rule_id)
    return f'<span class="rule-name" title="{rule_id}">{display_name}</span>'


def render_trend_chart(data: Sequence[Tuple[str, int, int, int]]) -> str:
    """Render SVG trend chart for daily statistics."""
    points = list(data)
    if not points:
        return "<p class='muted'>暂无数据</p>"

    points.sort(key=lambda x: x[0])
    width = 760
    height = 240
    pad = 36
    max_val = max(max(p[1] or 0, p[2] or 0, p[3] or 0) for p in points) or 1
    span_x = max(len(points) - 1, 1)

    def _x(i: int) -> float:
        return pad + (width - pad * 2) * (i / span_x)

    def _y(v: int) -> float:
        return pad + (height - pad * 2) * (1 - (v / max_val))

    totals = " ".join(f"{_x(i):.1f},{_y(p[1] or 0):.1f}" for i, p in enumerate(points))
    warns = " ".join(f"{_x(i):.1f},{_y(p[2] or 0):.1f}" for i, p in enumerate(points))
    errs = " ".join(f"{_x(i):.1f},{_y(p[3] or 0):.1f}" for i, p in enumerate(points))

    labels = [points[0][0], points[len(points) // 2][0], points[-1][0]]
    label_x = [_x(0), _x(len(points) // 2), _x(len(points) - 1)]
    label_html = "".join(
        f"<text x='{label_x[i]:.1f}' y='{height - 8}' font-size='11' text-anchor='middle' fill='#666'>{labels[i]}</text>"
        for i in range(len(labels))
    )

    return f"""
    <div class="chart">
      <svg viewBox="0 0 {width} {height}" width="100%" height="{height}">
        <rect x="0" y="0" width="{width}" height="{height}" fill="#fff" stroke="#efe5d7" rx="14" />
        <line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" stroke="#d8d0c4" />
        <line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" stroke="#d8d0c4" />
        <polyline fill="none" stroke="#1f7a5b" stroke-width="2.5" points="{totals}" />
        <polyline fill="none" stroke="#d97706" stroke-width="2" points="{warns}" />
        <polyline fill="none" stroke="#b00020" stroke-width="2" points="{errs}" />
        {label_html}
      </svg>
      <div class="legend">
        <span class="legend-item"><i style="background:#1f7a5b"></i>Total</span>
        <span class="legend-item"><i style="background:#d97706"></i>Warning</span>
        <span class="legend-item"><i style="background:#b00020"></i>Error</span>
      </div>
    </div>
    """


def render_project_option(project: Tuple[str, str], selected_key: Optional[str]) -> str:
    """Render a project option for select dropdown."""
    token_sep = "|||"
    key = project[0] or ""
    name = project[1] or ""
    token = f"{key}{token_sep}{name}"
    label = name or key or "(unknown)"
    selected = "selected" if selected_key == token else ""
    return f"<option value='{token}' {selected}>{label}</option>"
