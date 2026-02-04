"""Dashboard page template for BiliObjCLint server."""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

from .styles import STYLE
from .components import (
    render_trend_chart,
    render_project_option,
    render_rule_name,
    render_ios_switch,
)


def render_dashboard(
    username: str,
    role: str,
    projects: Sequence[Tuple[str, str]],
    daily: Iterable[Tuple[str, int, int, int]],
    rules: Iterable[Tuple[str, str, int, int]],
    autofix: dict,
    project_token: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    chart_data: Sequence[Tuple[str, int, int, int]],
) -> str:
    """Render the dashboard page."""
    proj_options = "".join(render_project_option(p, project_token) for p in projects)
    daily_rows = "".join(
        f"<tr><td>{d[0]}</td><td>{d[1] or 0}</td><td>{d[2] or 0}</td><td>{d[3] or 0}</td></tr>"
        for d in daily
    )
    # Rule rows with Chinese names (tooltip shows English ID) and iOS-style toggle
    rule_rows = "".join(
        f"<tr><td>{render_rule_name(r[0])}</td><td>{r[3]}</td><td>{r[1]}</td><td>{render_ios_switch(r[2])}</td></tr>"
        for r in rules
    )

    chart_html = render_trend_chart(chart_data)

    return f"""
    <html><head><title>Dashboard</title>{STYLE}</head><body>
      <div class="container">
        <header>
          <div class="brand">
            <h1>Lint Dashboard</h1>
            <p>代码问题趋势与规则统计总览</p>
          </div>
          <div class="nav">
            <span class="badge">{username} · {role}</span>
            <a href="/admin/users">用户管理</a>
            <a href="/logout">退出</a>
          </div>
        </header>

        <div class="card">
          <form method="get" action="/dashboard" class="form-row">
            <label>项目
              <select name="project"><option value="">全部</option>{proj_options}</select>
            </label>
            <label>开始日期
              <input type="date" name="start" value="{start_date or ''}" />
            </label>
            <label>结束日期
              <input type="date" name="end" value="{end_date or ''}" />
            </label>
            <button type="submit">刷新</button>
          </form>
          <p class="muted" style="margin-top:8px;">不填日期则展示全部数据。</p>
        </div>

        <div class="card">
          <h3>趋势图（{('筛选范围' if (start_date or end_date) else '近 7 天')}）</h3>
          {chart_html}
        </div>

        <div class="card">
          <h3>Autofix 汇总</h3>
          <div class="stat-grid">
            <div class="stat"><div class="label">Attempts</div><div class="value">{autofix.get('attempts', 0)}</div></div>
            <div class="stat"><div class="label">Success</div><div class="value">{autofix.get('success', 0)}</div></div>
            <div class="stat"><div class="label">Failed</div><div class="value">{autofix.get('failed', 0)}</div></div>
            <div class="stat"><div class="label">Cancelled</div><div class="value">{autofix.get('cancelled', 0)}</div></div>
            <div class="stat"><div class="label">Target Total</div><div class="value">{autofix.get('target_total', 0)}</div></div>
          </div>
        </div>

        <div class="card">
          <h3>每日统计</h3>
          <table class="table">
            <thead><tr><th>日期</th><th>总数</th><th>Warning</th><th>Error</th></tr></thead>
            <tbody>{daily_rows or '<tr><td colspan="4">暂无数据</td></tr>'}</tbody>
          </table>
        </div>

        <div class="card">
          <h3>规则统计</h3>
          <table class="table">
            <thead><tr><th>规则</th><th>数量</th><th>级别</th><th>启用</th></tr></thead>
            <tbody>{rule_rows or '<tr><td colspan="4">暂无数据</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    </body></html>
    """
