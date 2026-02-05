"""Shared UI components for BiliObjCLint server."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional, Sequence, Tuple

def get_rule_display_name(rule_id: str, rule_name: Optional[str] = None) -> str:
    """Get display name for a rule.

    Args:
        rule_id: Rule identifier (e.g., "forbidden_api")
        rule_name: Display name from Violation.rule_name

    Returns:
        Display name for UI (rule_name if available, else rule_id)
    """
    return rule_name or rule_id


def render_ios_switch(enabled: bool) -> str:
    """Render an iOS-style toggle switch (read-only)."""
    on_class = "on" if enabled else ""
    return f'<span class="ios-switch {on_class}"><span class="slider"></span></span>'


def render_rule_name(rule_id: str, rule_name: Optional[str] = None) -> str:
    """Render rule name with tooltip showing rule_id.

    Args:
        rule_id: Rule identifier
        rule_name: Display name from Violation.rule_name
    """
    display_name = rule_name or rule_id
    return f'<span class="rule-name" title="{rule_id}">{display_name}</span>'


def _fill_time_slots(
    data: Sequence[Tuple[str, int, int, int]],
    granularity: str = "day",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list:
    """Fill in missing time slots with zero values.

    Args:
        data: List of (time_slot, total, warning, error) tuples
              - For day granularity: time_slot is "YYYY-MM-DD"
              - For hour granularity: time_slot is "YYYY-MM-DDTHH"
        granularity: "hour" or "day"
        start_date: Custom start date (YYYY-MM-DD)
        end_date: Custom end date (YYYY-MM-DD)

    Returns:
        Complete list with all time slots filled in
    """
    # Build lookup from existing data
    data_map: Dict[str, Tuple[int, int, int]] = {}
    for row in data:
        data_map[row[0]] = (row[1] or 0, row[2] or 0, row[3] or 0)

    # Determine date range
    now = datetime.now()
    today = now.date()

    if start_date and end_date:
        try:
            d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            d_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            d_start = today - timedelta(days=6)
            d_end = today
    elif start_date:
        try:
            d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            d_end = today
        except ValueError:
            d_start = today - timedelta(days=6)
            d_end = today
    elif end_date:
        try:
            d_end = datetime.strptime(end_date, "%Y-%m-%d").date()
            d_start = d_end - timedelta(days=6)
        except ValueError:
            d_start = today - timedelta(days=6)
            d_end = today
    else:
        # Default: last 7 days
        d_end = today
        d_start = today - timedelta(days=6)

    result = []

    if granularity == "hour":
        # Hourly granularity: generate all hours for the date range
        current = datetime.combine(d_start, datetime.min.time())
        end_dt = datetime.combine(d_end, datetime.min.time()) + timedelta(days=1)
        # For same-day query ending today, only go up to current hour
        if d_end == today:
            end_dt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        while current < end_dt:
            slot_str = current.strftime("%Y-%m-%dT%H")
            if slot_str in data_map:
                total, warning, error = data_map[slot_str]
                result.append((slot_str, total, warning, error))
            else:
                result.append((slot_str, 0, 0, 0))
            current += timedelta(hours=1)
    else:
        # Daily granularity
        current = d_start
        while current <= d_end:
            date_str = current.strftime("%Y-%m-%d")
            if date_str in data_map:
                total, warning, error = data_map[date_str]
                result.append((date_str, total, warning, error))
            else:
                result.append((date_str, 0, 0, 0))
            current += timedelta(days=1)

    return result


def _format_label(time_slot: str, granularity: str) -> str:
    """Format time slot for display on X-axis.

    Args:
        time_slot: "YYYY-MM-DD" or "YYYY-MM-DDTHH"
        granularity: "hour" or "day"

    Returns:
        Formatted label string
    """
    if granularity == "hour":
        # "2026-02-04T10" -> "10:00"
        if "T" in time_slot:
            hour = time_slot.split("T")[1]
            return f"{hour}:00"
        return time_slot
    else:
        # "2026-02-04" -> "02-04"
        parts = time_slot.split("-")
        if len(parts) >= 3:
            return f"{parts[1]}-{parts[2]}"
        return time_slot


def render_trend_chart(
    data: Sequence[Tuple[str, int, int, int]],
    granularity: str = "day",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Render SVG trend chart for statistics.

    Args:
        data: List of (time_slot, total, warning, error) tuples
        granularity: "hour" or "day"
        start_date: Custom start date filter (YYYY-MM-DD)
        end_date: Custom end date filter (YYYY-MM-DD)
    """
    # Fill in missing time slots
    points = _fill_time_slots(data, granularity, start_date, end_date)

    if not points:
        return "<p class='muted'>暂无数据</p>"

    width = 760
    height = 240
    pad = 50  # Increased padding for labels
    max_val = max(max(p[1] or 0, p[2] or 0, p[3] or 0) for p in points) or 1
    span_x = max(len(points) - 1, 1)

    def _x(i: int) -> float:
        return pad + (width - pad * 2) * (i / span_x)

    def _y(v: int) -> float:
        return pad + (height - pad * 2) * (1 - (v / max_val))

    totals = " ".join(f"{_x(i):.1f},{_y(p[1] or 0):.1f}" for i, p in enumerate(points))
    warns = " ".join(f"{_x(i):.1f},{_y(p[2] or 0):.1f}" for i, p in enumerate(points))
    errs = " ".join(f"{_x(i):.1f},{_y(p[3] or 0):.1f}" for i, p in enumerate(points))

    # Generate circle markers for each data point (only for non-zero values)
    # Each circle has a <title> element for tooltip showing the count
    total_circles = "".join(
        f"<circle cx='{_x(i):.1f}' cy='{_y(p[1] or 0):.1f}' r='4' fill='#1f7a5b'>"
        f"<title>{_format_label(p[0], granularity)} 总数: {p[1] or 0}</title></circle>"
        for i, p in enumerate(points) if (p[1] or 0) > 0
    )
    warn_circles = "".join(
        f"<circle cx='{_x(i):.1f}' cy='{_y(p[2] or 0):.1f}' r='3.5' fill='#d97706'>"
        f"<title>{_format_label(p[0], granularity)} 警告: {p[2] or 0}</title></circle>"
        for i, p in enumerate(points) if (p[2] or 0) > 0
    )
    err_circles = "".join(
        f"<circle cx='{_x(i):.1f}' cy='{_y(p[3] or 0):.1f}' r='3.5' fill='#b00020'>"
        f"<title>{_format_label(p[0], granularity)} 错误: {p[3] or 0}</title></circle>"
        for i, p in enumerate(points) if (p[3] or 0) > 0
    )

    # Generate X-axis labels based on number of points
    num_points = len(points)
    if num_points <= 7:
        # Show all labels for 7 or fewer points
        label_indices = list(range(num_points))
    elif num_points <= 24:
        # For hourly data (up to 24 hours), show ~6 labels
        step = max(1, num_points // 6)
        label_indices = list(range(0, num_points, step))
        if (num_points - 1) not in label_indices:
            label_indices.append(num_points - 1)
    else:
        # For many points, show first, 1/4, 1/2, 3/4, last
        label_indices = [0, num_points // 4, num_points // 2, 3 * num_points // 4, num_points - 1]

    label_html = "".join(
        f"<text x='{_x(i):.1f}' y='{height - 8}' font-size='10' text-anchor='middle' fill='#666'>"
        f"{_format_label(points[i][0], granularity)}</text>"
        for i in label_indices
    )

    # Y-axis labels
    y_labels = ""
    for i in range(5):
        val = int(max_val * (1 - i / 4))
        y_pos = _y(val)
        y_labels += f"<text x='{pad - 8}' y='{y_pos + 4:.1f}' font-size='10' text-anchor='end' fill='#999'>{val}</text>"

    # Granularity indicator
    granularity_text = "按小时" if granularity == "hour" else "按天"

    return f"""
    <div class="chart">
      <svg viewBox="0 0 {width} {height}" width="100%" height="{height}">
        <rect x="0" y="0" width="{width}" height="{height}" fill="#fff" stroke="#efe5d7" rx="14" />
        <line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" stroke="#d8d0c4" />
        <line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" stroke="#d8d0c4" />
        {y_labels}
        <polyline fill="none" stroke="#1f7a5b" stroke-width="2.5" points="{totals}" />
        <polyline fill="none" stroke="#d97706" stroke-width="2" points="{warns}" />
        <polyline fill="none" stroke="#b00020" stroke-width="2" points="{errs}" />
        {total_circles}
        {warn_circles}
        {err_circles}
        {label_html}
      </svg>
      <div class="legend">
        <span class="legend-item"><i style="background:#1f7a5b"></i>总数</span>
        <span class="legend-item"><i style="background:#d97706"></i>警告</span>
        <span class="legend-item"><i style="background:#b00020"></i>错误</span>
        <span class="muted" style="margin-left:auto;">({granularity_text})</span>
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
