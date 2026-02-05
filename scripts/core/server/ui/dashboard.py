"""Dashboard page template for BiliObjCLint server."""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from .styles import STYLE
from .components import (
    render_trend_chart,
    render_rule_name,
    render_ios_switch,
    get_rule_display_name,
)


DASHBOARD_SCRIPT = """
<script>
// 级联选择: project_key → project_name
document.addEventListener('DOMContentLoaded', function() {
    const projectKeySelect = document.getElementById('project_key_select');
    const projectNameSelect = document.getElementById('project_name_select');

    if (projectKeySelect && projectNameSelect) {
        projectKeySelect.addEventListener('change', function() {
            const projectKey = this.value;
            // 清空 project_name 选择
            projectNameSelect.innerHTML = '<option value="">全部</option>';

            if (!projectKey) return;

            // 获取 project_names
            fetch('/api/v1/project_names?project_key=' + encodeURIComponent(projectKey))
                .then(response => response.json())
                .then(data => {
                    if (data.project_names) {
                        data.project_names.forEach(function(name) {
                            const option = document.createElement('option');
                            option.value = name;
                            option.textContent = name;
                            projectNameSelect.appendChild(option);
                        });
                    }
                })
                .catch(err => console.error('Failed to load project names:', err));
        });
    }
});
</script>
"""


def render_dashboard(
    username: str,
    role: str,
    project_keys: Sequence[str],
    project_names: Sequence[str],
    selected_project_key: Optional[str],
    selected_project_name: Optional[str],
    daily: Iterable[Tuple[str, int, int, int]],
    rules: Iterable[Tuple[str, str, str, int, int]],
    autofix: dict,
    start_date: Optional[str],
    end_date: Optional[str],
    chart_data: Sequence[Tuple[str, int, int, int]],
    chart_granularity: str = "day",
    new_violation_types: Optional[List[Tuple[str, Optional[str], Optional[str], int]]] = None,
) -> str:
    """Render the dashboard page.

    Args:
        username: Current user's username
        role: Current user's role
        project_keys: List of available project keys
        project_names: List of project names for selected project_key
        selected_project_key: Currently selected project key
        selected_project_name: Currently selected project name
        daily: Daily statistics data
        rules: Rule statistics data
        autofix: Autofix summary data
        start_date: Start date filter
        end_date: End date filter
        chart_data: Trend chart data
        chart_granularity: Chart granularity ("day" or "hour")
        new_violation_types: Today's new violation types (rule_id, sub_type, count)
    """
    # 构建 project_key 下拉选项
    pk_options = "".join(
        f"<option value=\"{pk}\" {'selected' if pk == selected_project_key else ''}>{pk}</option>"
        for pk in project_keys
    )

    # 构建 project_name 下拉选项
    pn_options = "".join(
        f"<option value=\"{pn}\" {'selected' if pn == selected_project_name else ''}>{pn}</option>"
        for pn in project_names
    )

    # 每日统计行
    daily_rows = "".join(
        f"<tr><td>{d[0]}</td><td>{d[1] or 0}</td><td>{d[2] or 0}</td><td>{d[3] or 0}</td></tr>"
        for d in daily
    )

    # 规则统计行（可点击跳转到违规列表）
    rule_rows_list = []
    for r in rules:
        rule_id, rule_name, severity, enabled, count = r
        display_name = render_rule_name(rule_id, rule_name)
        toggle = render_ios_switch(enabled)
        # 构建违规列表链接
        if selected_project_key and selected_project_name:
            link = f"/violations?project_key={selected_project_key}&project_name={selected_project_name}&rule_id={rule_id}"
            row = f"<tr class='clickable-row' onclick=\"window.location='{link}'\"><td>{display_name}</td><td>{count}</td><td>{severity}</td><td>{toggle}</td></tr>"
        else:
            row = f"<tr><td>{display_name}</td><td>{count}</td><td>{severity}</td><td>{toggle}</td></tr>"
        rule_rows_list.append(row)
    rule_rows = "".join(rule_rows_list)

    # 新增 Violation Type 卡片
    new_types_html = ""
    if new_violation_types:
        new_types_rows = "".join(
            f"<tr><td>{get_rule_display_name(t[0], t[1])}</td><td>{t[2] or '-'}</td><td>{t[3]}</td></tr>"
            for t in new_violation_types
        )
        new_types_html = f"""
        <div class="card">
          <h3>今日新增 Violation Type <span class="badge-new">{len(new_violation_types)} 种</span></h3>
          <p class="muted">今日首次出现的 (rule_id, sub_type) 组合</p>
          <table class="table">
            <thead><tr><th>规则</th><th>子类型</th><th>数量</th></tr></thead>
            <tbody>{new_types_rows or '<tr><td colspan="3">暂无新增</td></tr>'}</tbody>
          </table>
        </div>
        """
    elif selected_project_key and selected_project_name:
        new_types_html = """
        <div class="card">
          <h3>今日新增 Violation Type <span class="badge-ok">0 种</span></h3>
          <p class="muted">今日无新增的违规类型，保持得很好！</p>
        </div>
        """

    chart_html = render_trend_chart(chart_data, granularity=chart_granularity, start_date=start_date, end_date=end_date)

    return f"""
    <html><head><title>Dashboard</title>{STYLE}
    <style>
    .clickable-row {{ cursor: pointer; }}
    .clickable-row:hover {{ background: #faf6f0; }}
    .badge-new {{ background: #fee2e2; color: #b91c1c; padding: 2px 8px; border-radius: 10px; font-size: 12px; margin-left: 8px; }}
    .badge-ok {{ background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 10px; font-size: 12px; margin-left: 8px; }}
    </style>
    {DASHBOARD_SCRIPT}
    </head><body>
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
            <label>项目组
              <select name="project_key" id="project_key_select">
                <option value="">全部</option>
                {pk_options}
              </select>
            </label>
            <label>项目名称
              <select name="project_name" id="project_name_select">
                <option value="">全部</option>
                {pn_options}
              </select>
            </label>
            <label>开始日期
              <input type="date" name="start" value="{start_date or ''}" />
            </label>
            <label>结束日期
              <input type="date" name="end" value="{end_date or ''}" />
            </label>
            <button type="submit">刷新</button>
          </form>
          <p class="muted" style="margin-top:8px;">选择项目组后可进一步筛选项目名称。不填日期则展示全部数据。</p>
        </div>

        <div class="card">
          <h3>趋势图（{('筛选范围' if (start_date or end_date) else '近 7 天')}）</h3>
          {chart_html}
        </div>

        <div class="card">
          <h3>Autofix 汇总</h3>
          <div class="stat-grid">
            <div class="stat"><div class="label">尝试次数</div><div class="value">{autofix.get('attempts', 0)}</div></div>
            <div class="stat"><div class="label">成功</div><div class="value">{autofix.get('success', 0)}</div></div>
            <div class="stat"><div class="label">失败</div><div class="value">{autofix.get('failed', 0)}</div></div>
            <div class="stat"><div class="label">已取消</div><div class="value">{autofix.get('cancelled', 0)}</div></div>
            <div class="stat"><div class="label">目标总数</div><div class="value">{autofix.get('target_total', 0)}</div></div>
          </div>
        </div>

        <div class="card">
          <h3>每日统计</h3>
          <table class="table">
            <thead><tr><th>日期</th><th>总数</th><th>警告</th><th>错误</th></tr></thead>
            <tbody>{daily_rows or '<tr><td colspan="4">暂无数据</td></tr>'}</tbody>
          </table>
        </div>

        {new_types_html}

        <div class="card">
          <h3>规则统计</h3>
          <p class="muted">{'点击规则行可查看该规则的所有违规详情' if (selected_project_key and selected_project_name) else '选择具体项目后，可点击规则行查看违规详情'}</p>
          <table class="table">
            <thead><tr><th>规则</th><th>数量</th><th>级别</th><th>启用</th></tr></thead>
            <tbody>{rule_rows or '<tr><td colspan="4">暂无数据</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    </body></html>
    """
