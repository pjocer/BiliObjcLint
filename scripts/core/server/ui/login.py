"""Login page template for BiliObjCLint server."""
from __future__ import annotations

from .styles import STYLE

LOGIN_STYLE = """
<style>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  padding: 20px;
}

.login-card {
  background: #fff;
  border-radius: 20px;
  padding: 40px 36px;
  width: 100%;
  max-width: 380px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.1);
  text-align: center;
}

.login-logo {
  width: 80px;
  height: 80px;
  margin: 0 auto 16px;
  border-radius: 16px;
  object-fit: contain;
}

.login-card h2 {
  margin: 0 0 8px;
  font-size: 24px;
  color: #1e1e1e;
}

.login-card .subtitle {
  color: #6b6b6b;
  font-size: 14px;
  margin-bottom: 28px;
}

.login-card .form-group {
  margin-bottom: 16px;
  text-align: left;
}

.login-card .form-group label {
  display: block;
  font-size: 13px;
  color: #6b6b6b;
  margin-bottom: 6px;
}

.login-card .form-group input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid #e6ded4;
  border-radius: 10px;
  font-size: 15px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.login-card .form-group input:focus {
  outline: none;
  border-color: #1f7a5b;
  box-shadow: 0 0 0 3px rgba(31, 122, 91, 0.1);
}

.login-card .submit-btn {
  width: 100%;
  padding: 14px;
  background: linear-gradient(135deg, #1f7a5b 0%, #2a9d70 100%);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  margin-top: 8px;
}

.login-card .submit-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(31, 122, 91, 0.3);
}

.login-card .error {
  background: #fef2f2;
  color: #b91c1c;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 16px;
  text-align: left;
}
</style>
"""


def render_login(error: str = "") -> str:
    """Render the login page."""
    err = f'<div class="error">{error}</div>' if error else ""
    return f"""
    <html>
    <head>
      <title>Login - BiliObjCLint</title>
      {STYLE}
      {LOGIN_STYLE}
    </head>
    <body>
      <div class="login-page">
        <div class="login-card">
          <img class="login-logo" src="/static/biliobjclint_logo.png" alt="BiliObjCLint" />
          <h2>BiliObjCLint</h2>
          <p class="subtitle">代码质量统计平台</p>
          {err}
          <form method="post" action="/login">
            <div class="form-group">
              <label>用户名</label>
              <input name="username" placeholder="请输入用户名" autocomplete="username" />
            </div>
            <div class="form-group">
              <label>密码</label>
              <input name="password" type="password" placeholder="请输入密码" autocomplete="current-password" />
            </div>
            <button type="submit" class="submit-btn">登 录</button>
          </form>
        </div>
      </div>
    </body>
    </html>
    """
