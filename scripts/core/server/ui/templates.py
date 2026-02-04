"""HTML templates and styling for BiliObjCLint server."""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

STYLE = """
<style>
:root {
  --bg-1: #f7f2ea;
  --bg-2: #e8f1e9;
  --ink: #1e1e1e;
  --muted: #6b6b6b;
  --accent: #1f7a5b;
  --accent-2: #d97706;
  --card: #ffffff;
  --border: #e6ded4;
  --shadow: 0 18px 50px rgba(0,0,0,0.08);
  --radius: 16px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: "Space Grotesk", "IBM Plex Sans", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
  color: var(--ink);
  background: radial-gradient(1200px 600px at 10% 10%, #fff6e8 0%, transparent 60%),
              radial-gradient(900px 500px at 90% 0%, #e3f4e9 0%, transparent 60%),
              linear-gradient(180deg, var(--bg-1) 0%, var(--bg-2) 100%);
  min-height: 100vh;
}

.container {
  max-width: 1120px;
  margin: 0 auto;
  padding: 32px 24px 64px;
}

header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.brand {
  display: flex;
  flex-direction: column;
}

.brand h1 {
  margin: 0;
  font-size: 32px;
  letter-spacing: -0.02em;
}

.brand p {
  margin: 6px 0 0 0;
  color: var(--muted);
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: #f2eee7;
  font-size: 12px;
}

.nav a {
  color: var(--ink);
  text-decoration: none;
  margin-right: 12px;
  font-weight: 600;
}

.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 22px;
  margin: 18px 0;
  box-shadow: var(--shadow);
  animation: floatIn 0.6s ease both;
}

@keyframes floatIn {
  from { transform: translateY(8px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.form-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: center;
}

input, select {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 14px;
  min-width: 160px;
  background: #fff;
}

button {
  padding: 10px 16px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

button:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(31, 122, 91, 0.25);
}

.table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 10px;
}

.table th, .table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  font-size: 14px;
}

.table th {
  background: #f6f1ea;
  color: #3d3d3d;
}

.table tr:nth-child(even) td {
  background: #fbf8f2;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px;
}

.stat {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 14px;
  background: #fff;
}

.stat .label { color: var(--muted); font-size: 12px; }
.stat .value { font-size: 22px; font-weight: 700; }

.muted { color: var(--muted); font-size: 12px; }

.chart { display: flex; flex-direction: column; gap: 10px; }
.legend { display: flex; gap: 12px; font-size: 12px; color: var(--muted); }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.legend-item i { display: inline-block; width: 12px; height: 12px; border-radius: 999px; }

.error { color: #b00020; }
.warn { color: #b26a00; }

.login-wrapper {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(300px, 420px);
  gap: 32px;
  align-items: center;
}

.login-panel {
  background: #fff;
  border-radius: 20px;
  padding: 24px;
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
}

.hero {
  padding: 24px;
}

.hero h2 {
  margin: 0 0 10px;
  font-size: 30px;
}

.hero p {
  color: var(--muted);
}

@media (max-width: 800px) {
  .login-wrapper { grid-template-columns: 1fr; }
  header { flex-direction: column; align-items: flex-start; }
}
</style>
"""


def render_login(error: str = "") -> str:
    err = f"<p class='error'>{error}</p>" if error else ""
    return f"""
    <html><head><title>Login</title>{STYLE}</head>
    <body>
      <div class="container login-wrapper">
        <div class="hero">
          <h2>BiliObjCLint Server</h2>
          <p>本地统计服务，集中查看三个月内的代码问题趋势与自动修复表现。</p>
          <div class="stat-grid">
            <div class="stat"><div class="label">模块</div><div class="value">Lint</div></div>
            <div class="stat"><div class="label">安全</div><div class="value">Intranet</div></div>
            <div class="stat"><div class="label">模式</div><div class="value">Local</div></div>
          </div>
        </div>
        <div class="login-panel">
          <h3>登录</h3>
          {err}
          <form method="post" action="/login">
            <div class="form-row">
              <label>用户名<br/><input name="username" /></label>
            </div>
            <div class="form-row" style="margin-top:10px;">
              <label>密码<br/><input name="password" type="password" /></label>
            </div>
            <div style="margin-top:16px;">
              <button type="submit">进入控制台</button>
            </div>
          </form>
        </div>
      </div>
    </body></html>
    """


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
    proj_options = "".join(_project_option(p, project_token) for p in projects)
    daily_rows = "".join(
        f"<tr><td>{d[0]}</td><td>{d[1] or 0}</td><td>{d[2] or 0}</td><td>{d[3] or 0}</td></tr>"
        for d in daily
    )
    rule_rows = "".join(
        f"<tr><td>{r[0]}</td><td>{r[3]}</td><td>{r[1]}</td><td>{'Y' if r[2] else 'N'}</td></tr>"
        for r in rules
    )

    chart_html = _render_trend_chart(chart_data)

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
            <thead><tr><th>规则</th><th>数量</th><th>Severity</th><th>Enabled</th></tr></thead>
            <tbody>{rule_rows or '<tr><td colspan="4">暂无数据</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    </body></html>
    """


def _render_trend_chart(data: Sequence[Tuple[str, int, int, int]]) -> str:
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


def _project_option(project: Tuple[str, str], selected_key: Optional[str]) -> str:
    token_sep = "|||"
    key = project[0] or ""
    name = project[1] or ""
    token = f"{key}{token_sep}{name}"
    label = name or key or "(unknown)"
    selected = "selected" if selected_key == token else ""
    return f"<option value='{token}' {selected}>{label}</option>"


def render_users(users, error: str = "") -> str:
    rows = "".join(
        f"<tr><td>{u[0]}</td><td>{u[1]}</td><td>{u[2]}</td><td><a href='/admin/users?delete={u[0]}'>删除</a></td></tr>"
        for u in users
    )
    err = f"<p class='error'>{error}</p>" if error else ""
    return f"""
    <html><head><title>Users</title>{STYLE}</head><body>
      <div class="container">
        <header>
          <div class="brand">
            <h1>用户管理</h1>
            <p>账号与角色配置</p>
          </div>
          <div class="nav">
            <a href="/dashboard">返回 Dashboard</a>
          </div>
        </header>

        <div class="card">
          <h3>用户列表</h3>
          {err}
          <table class="table">
            <thead><tr><th>用户名</th><th>角色</th><th>创建时间</th><th>操作</th></tr></thead>
            <tbody>{rows or '<tr><td colspan="4">暂无用户</td></tr>'}</tbody>
          </table>
        </div>

        <div class="card">
          <h3>新增用户</h3>
          <form method="post" action="/admin/users">
            <div class="form-row">
              <label>用户名<br/><input name="username" /></label>
              <label>密码<br/><input name="password" type="password" /></label>
              <label>角色<br/>
                <select name="role">
                  <option value="readonly">readonly</option>
                  <option value="admin">admin</option>
                </select>
              </label>
            </div>
            <div style="margin-top:12px;">
              <button type="submit">创建用户</button>
            </div>
          </form>
        </div>
      </div>
    </body></html>
    """
