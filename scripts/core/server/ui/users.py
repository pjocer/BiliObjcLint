"""User management page template for BiliObjCLint server."""
from __future__ import annotations

from .styles import STYLE


def render_users(users, error: str = "") -> str:
    """Render the user management page."""
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
