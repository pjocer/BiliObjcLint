"""Violations page templates for BiliObjCLint server."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .styles import STYLE
from .components import get_rule_display_name


def render_violations_list(
    username: str,
    role: str,
    project_key: str,
    project_name: str,
    violations: List[Dict[str, Any]],
    total: int,
    page: int,
    total_pages: int,
    rule_id: Optional[str] = None,
    sub_type: Optional[str] = None,
    search: Optional[str] = None,
) -> str:
    """Render the violations list page.

    Args:
        username: Current user's username
        role: Current user's role
        project_key: Project key
        project_name: Project name
        violations: List of violation dictionaries
        total: Total count of violations
        page: Current page number
        total_pages: Total number of pages
        rule_id: Filter by rule ID
        sub_type: Filter by sub type
        search: Search query
    """
    # 构建过滤条件描述
    filter_desc = []
    if rule_id:
        filter_desc.append(f"规则: {get_rule_display_name(rule_id)}")
    if sub_type:
        filter_desc.append(f"子类型: {sub_type}")
    if search:
        filter_desc.append(f"搜索: {search}")
    filter_text = " | ".join(filter_desc) if filter_desc else "全部"

    # 构建违规行
    violation_rows = []
    for v in violations:
        vid = v.get("violation_id", "")
        file_path = v.get("file_path", "")
        line = v.get("line", 0)
        rid = v.get("rule_id", "")
        st = v.get("sub_type") or "-"
        severity = v.get("severity", "warning")
        message = v.get("message", "")[:80]  # 截断消息
        if len(v.get("message", "")) > 80:
            message += "..."

        # 文件路径截断显示
        display_path = file_path
        if len(file_path) > 50:
            display_path = "..." + file_path[-47:]

        detail_link = f"/violations/{vid}?project_key={project_key}&project_name={project_name}"
        severity_class = "error" if severity == "error" else "warning"

        # 优先使用 violation 自带的 rule_name
        rule_display = get_rule_display_name(rid, v.get("rule_name"))
        row = f"""
        <tr class="clickable-row" onclick="window.location='{detail_link}'">
            <td title="{file_path}">{display_path}:{line}</td>
            <td>{rule_display}</td>
            <td>{st}</td>
            <td><span class="severity-{severity_class}">{severity}</span></td>
            <td title="{v.get('message', '')}">{message}</td>
        </tr>
        """
        violation_rows.append(row)

    rows_html = "".join(violation_rows) or '<tr><td colspan="5">暂无违规记录</td></tr>'

    # 构建分页
    pagination_html = _render_pagination(
        page, total_pages, project_key, project_name, rule_id, sub_type, search
    )

    # 构建搜索表单
    search_value = search or ""

    return f"""
    <html><head><title>Violations - {project_name}</title>{STYLE}
    <style>
    .clickable-row {{ cursor: pointer; }}
    .clickable-row:hover {{ background: #faf6f0; }}
    .severity-error {{ color: #b91c1c; font-weight: 600; }}
    .severity-warning {{ color: #d97706; }}
    .pagination {{ display: flex; gap: 8px; margin-top: 16px; justify-content: center; align-items: center; }}
    .pagination a, .pagination span {{ padding: 6px 12px; border-radius: 6px; text-decoration: none; }}
    .pagination a {{ background: #f5f0e8; color: #333; }}
    .pagination a:hover {{ background: #efe5d7; }}
    .pagination .current {{ background: #fb7299; color: #fff; }}
    .pagination .disabled {{ color: #999; }}
    .search-form {{ display: flex; gap: 8px; margin-bottom: 16px; }}
    .search-form input[type="text"] {{ flex: 1; padding: 8px 12px; border: 1px solid #e6ded4; border-radius: 8px; }}
    .search-form button {{ padding: 8px 16px; background: #fb7299; color: #fff; border: none; border-radius: 8px; cursor: pointer; }}
    .filter-info {{ color: #6b6b6b; font-size: 14px; margin-bottom: 12px; }}
    .back-link {{ color: #fb7299; text-decoration: none; margin-bottom: 16px; display: inline-block; }}
    .back-link:hover {{ text-decoration: underline; }}
    </style>
    </head><body>
      <div class="container">
        <header>
          <div class="brand">
            <h1>Violations</h1>
            <p>{project_key} / {project_name}</p>
          </div>
          <div class="nav">
            <span class="badge">{username} · {role}</span>
            <a href="/dashboard?project_key={project_key}&project_name={project_name}">Dashboard</a>
            <a href="/logout">退出</a>
          </div>
        </header>

        <a class="back-link" href="/dashboard?project_key={project_key}&project_name={project_name}">← 返回 Dashboard</a>

        <div class="card">
          <form class="search-form" method="get" action="/violations">
            <input type="hidden" name="project_key" value="{project_key}" />
            <input type="hidden" name="project_name" value="{project_name}" />
            {f'<input type="hidden" name="rule_id" value="{rule_id}" />' if rule_id else ''}
            {f'<input type="hidden" name="sub_type" value="{sub_type}" />' if sub_type else ''}
            <input type="text" name="search" value="{search_value}" placeholder="搜索文件路径或消息内容..." />
            <button type="submit">搜索</button>
            {f'<a href="/violations?project_key={project_key}&project_name={project_name}" style="padding:8px 12px;color:#666;">清除筛选</a>' if (rule_id or sub_type or search) else ''}
          </form>
          <p class="filter-info">筛选条件: {filter_text} | 共 {total} 条违规</p>
        </div>

        <div class="card">
          <table class="table">
            <thead>
              <tr>
                <th>位置</th>
                <th>规则</th>
                <th>子类型</th>
                <th>级别</th>
                <th>消息</th>
              </tr>
            </thead>
            <tbody>
              {rows_html}
            </tbody>
          </table>
          {pagination_html}
        </div>
      </div>
    </body></html>
    """


def _render_pagination(
    page: int,
    total_pages: int,
    project_key: str,
    project_name: str,
    rule_id: Optional[str],
    sub_type: Optional[str],
    search: Optional[str],
) -> str:
    """Render pagination controls."""
    if total_pages <= 1:
        return ""

    # 构建基础 URL
    base_params = f"project_key={project_key}&project_name={project_name}"
    if rule_id:
        base_params += f"&rule_id={rule_id}"
    if sub_type:
        base_params += f"&sub_type={sub_type}"
    if search:
        base_params += f"&search={search}"

    parts = ['<div class="pagination">']

    # 上一页
    if page > 1:
        parts.append(f'<a href="/violations?{base_params}&page={page-1}">上一页</a>')
    else:
        parts.append('<span class="disabled">上一页</span>')

    # 页码
    # 显示: 1 ... (page-1) page (page+1) ... total_pages
    pages_to_show = set()
    pages_to_show.add(1)
    pages_to_show.add(total_pages)
    for p in range(max(1, page - 1), min(total_pages, page + 1) + 1):
        pages_to_show.add(p)

    sorted_pages = sorted(pages_to_show)
    prev_p = 0
    for p in sorted_pages:
        if prev_p and p - prev_p > 1:
            parts.append('<span class="disabled">...</span>')
        if p == page:
            parts.append(f'<span class="current">{p}</span>')
        else:
            parts.append(f'<a href="/violations?{base_params}&page={p}">{p}</a>')
        prev_p = p

    # 下一页
    if page < total_pages:
        parts.append(f'<a href="/violations?{base_params}&page={page+1}">下一页</a>')
    else:
        parts.append('<span class="disabled">下一页</span>')

    parts.append('</div>')
    return "".join(parts)


def _highlight_objc_simple(code: str) -> str:
    """Simple ObjC syntax highlighting for server-side rendering.

    Args:
        code: Code line content (already HTML escaped)

    Returns:
        Code with syntax highlighting spans
    """
    import re

    # Keywords
    keywords = r'\b(if|else|for|while|do|switch|case|default|break|continue|return|goto|typedef|struct|enum|union|sizeof|static|extern|const|volatile|inline|void|char|short|int|long|float|double|bool|BOOL|YES|NO|nil|NULL|self|super|id|Class|SEL|IMP|instancetype)\b'
    code = re.sub(keywords, r'<span class="hl-keyword">\1</span>', code)

    # @keywords
    at_keywords = r'(@interface|@implementation|@end|@protocol|@property|@synthesize|@dynamic|@class|@public|@private|@protected|@selector|@try|@catch|@finally|@throw|@synchronized|@autoreleasepool)'
    code = re.sub(at_keywords, r'<span class="hl-at-keyword">\1</span>', code)

    # Property keywords
    prop_keywords = r'\b(nonatomic|atomic|strong|weak|copy|assign|retain|readonly|readwrite|nullable|nonnull)\b'
    code = re.sub(prop_keywords, r'<span class="hl-prop">\1</span>', code)

    # Numbers
    code = re.sub(r'\b(\d+\.?\d*[fFlL]?)\b', r'<span class="hl-number">\1</span>', code)

    return code


def render_violation_detail(
    username: str,
    role: str,
    project_key: str,
    project_name: str,
    violation: Dict[str, Any],
) -> str:
    """Render the violation detail page.

    Args:
        username: Current user's username
        role: Current user's role
        project_key: Project key
        project_name: Project name
        violation: Violation dictionary
    """
    vid = violation.get("violation_id", "")
    file_path = violation.get("file_path", "")
    line = violation.get("line", 0)
    column = violation.get("column", 0)
    rule_id = violation.get("rule_id", "")
    sub_type = violation.get("sub_type") or "-"
    severity = violation.get("severity", "warning")
    message = violation.get("message", "")
    code_hash = violation.get("code_hash", "")
    context = violation.get("context", "")
    related_lines = violation.get("related_lines")
    first_seen = violation.get("first_seen", "")
    last_seen = violation.get("last_seen", "")
    pod_name = violation.get("pod_name") or "-"

    severity_class = "error" if severity == "error" else "warning"

    # 格式化 context（代码上下文）- 按行显示带高亮
    context_html = ""
    if context:
        # 按行分割 context
        context_lines = context.split('\n') if '\n' in context else [context]

        # 计算行号起始位置
        if related_lines:
            start_line = related_lines[0]
        else:
            # 如果没有 related_lines，从 line 开始
            start_line = max(1, line - len(context_lines) // 2)

        code_lines_html = []
        for i, code_line in enumerate(context_lines):
            current_line_num = start_line + i
            # 问题行高亮
            highlighted = 'highlighted' if current_line_num == line else ''
            # HTML 转义
            escaped_line = code_line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            # 语法高亮
            highlighted_content = _highlight_objc_simple(escaped_line)
            code_lines_html.append(
                f'<div class="code-line {highlighted}">'
                f'<span class="code-line-num">{current_line_num}</span>'
                f'<span class="code-line-content">{highlighted_content}</span>'
                f'</div>'
            )

        context_html = '<div class="code-block">' + ''.join(code_lines_html) + '</div>'

    related_lines_html = ""
    if related_lines:
        related_lines_html = f"<p><strong>关联行范围:</strong> {related_lines[0]} - {related_lines[1]}</p>"

    back_link = f"/violations?project_key={project_key}&project_name={project_name}&rule_id={rule_id}"

    return f"""
    <html><head><title>Violation Detail</title>{STYLE}
    <style>
    .severity-error {{ color: #b91c1c; font-weight: 600; }}
    .severity-warning {{ color: #d97706; }}
    .back-link {{ color: #fb7299; text-decoration: none; margin-bottom: 16px; display: inline-block; }}
    .back-link:hover {{ text-decoration: underline; }}
    .detail-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }}
    .detail-item {{ padding: 12px; background: #faf6f0; border-radius: 8px; }}
    .detail-item .label {{ color: #6b6b6b; font-size: 12px; margin-bottom: 4px; }}
    .detail-item .value {{ color: #1e1e1e; font-size: 14px; word-break: break-all; }}
    .message-box {{ background: #fef9f3; border-left: 4px solid #fb7299; padding: 16px; margin: 16px 0; border-radius: 0 8px 8px 0; }}
    /* 代码块样式 - 与 Claude html_report 一致 */
    .code-block {{ background: #1e1e1e; border-radius: 8px; overflow: hidden; margin: 12px 0; }}
    .code-line {{ display: flex; padding: 2px 12px; }}
    .code-line.highlighted {{ background: rgba(255, 200, 0, 0.2); }}
    .code-line-num {{ min-width: 45px; padding-right: 12px; text-align: right; color: #858585; user-select: none; border-right: 1px solid #404040; margin-right: 12px; font-family: 'SF Mono', Monaco, monospace; font-size: 13px; }}
    .code-line-content {{ white-space: pre; color: #d4d4d4; font-family: 'SF Mono', Monaco, monospace; font-size: 13px; }}
    /* ObjC 语法高亮 */
    .hl-keyword {{ color: #569cd6; }}
    .hl-at-keyword {{ color: #c586c0; }}
    .hl-prop {{ color: #4ec9b0; }}
    .hl-string {{ color: #ce9178; }}
    .hl-number {{ color: #b5cea8; }}
    .hl-comment {{ color: #6a9955; font-style: italic; }}
    </style>
    </head><body>
      <div class="container">
        <header>
          <div class="brand">
            <h1>Violation Detail</h1>
            <p>{project_key} / {project_name}</p>
          </div>
          <div class="nav">
            <span class="badge">{username} · {role}</span>
            <a href="/dashboard?project_key={project_key}&project_name={project_name}">Dashboard</a>
            <a href="/logout">退出</a>
          </div>
        </header>

        <a class="back-link" href="{back_link}">← 返回违规列表</a>

        <div class="card">
          <h3>
            <span class="severity-{severity_class}">[{severity.upper()}]</span>
            {get_rule_display_name(rule_id, violation.get("rule_name"))}
          </h3>
          <div class="message-box">{message}</div>

          <div class="detail-grid">
            <div class="detail-item">
              <div class="label">文件路径</div>
              <div class="value">{file_path}</div>
            </div>
            <div class="detail-item">
              <div class="label">位置</div>
              <div class="value">行 {line}, 列 {column}</div>
            </div>
            <div class="detail-item">
              <div class="label">规则 ID</div>
              <div class="value">{rule_id}</div>
            </div>
            <div class="detail-item">
              <div class="label">子类型</div>
              <div class="value">{sub_type}</div>
            </div>
            <div class="detail-item">
              <div class="label">Pod 名称</div>
              <div class="value">{pod_name}</div>
            </div>
            <div class="detail-item">
              <div class="label">Code Hash</div>
              <div class="value">{code_hash or '-'}</div>
            </div>
            <div class="detail-item">
              <div class="label">首次发现</div>
              <div class="value">{first_seen}</div>
            </div>
            <div class="detail-item">
              <div class="label">最后更新</div>
              <div class="value">{last_seen}</div>
            </div>
          </div>

          {related_lines_html}
        </div>

        {f'<div class="card"><h3>代码上下文</h3>{context_html}</div>' if context_html else ''}

        <div class="card">
          <h3>标识信息</h3>
          <p><strong>Violation ID:</strong> <code>{vid}</code></p>
        </div>
      </div>
    </body></html>
    """
