"""Register page template for BiliObjCLint server."""
from __future__ import annotations

from .styles import STYLE

REGISTER_STYLE = """
<style>
.register-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  padding: 20px;
}

.register-card {
  background: #fff;
  border-radius: 20px;
  padding: 40px 36px;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.1);
  text-align: center;
}

.register-logo {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  border-radius: 16px;
  object-fit: contain;
}

.register-card h2 {
  margin: 0 0 8px;
  font-size: 24px;
  color: #1e1e1e;
}

.register-card .subtitle {
  color: #6b6b6b;
  font-size: 14px;
  margin-bottom: 28px;
}

.register-card .form-group {
  margin-bottom: 16px;
  text-align: left;
}

.register-card .form-group label {
  display: block;
  font-size: 13px;
  color: #6b6b6b;
  margin-bottom: 6px;
}

.register-card .form-group input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid #e6ded4;
  border-radius: 10px;
  font-size: 15px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.register-card .form-group input:focus {
  outline: none;
  border-color: #fb7299;
  box-shadow: 0 0 0 3px rgba(251, 114, 153, 0.15);
}

.register-card .submit-btn {
  width: 100%;
  padding: 14px;
  background: linear-gradient(135deg, #fb7299 0%, #f25d8e 100%);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  margin-top: 8px;
}

.register-card .submit-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(251, 114, 153, 0.4);
}

.register-card .error {
  background: #fef2f2;
  color: #b91c1c;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 16px;
  text-align: left;
}

.register-card .success {
  background: #f0fdf4;
  color: #166534;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 16px;
  text-align: left;
}

.register-card .login-link {
  margin-top: 20px;
  font-size: 14px;
  color: #6b6b6b;
}

.register-card .login-link a {
  color: #fb7299;
  text-decoration: none;
  font-weight: 600;
}

.register-card .login-link a:hover {
  text-decoration: underline;
}

.register-card .hint {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 4px;
}
</style>
"""


def render_register(error: str = "", success: str = "") -> str:
    """Render the register page."""
    err = f'<div class="error">{error}</div>' if error else ""
    succ = f'<div class="success">{success}</div>' if success else ""
    return f"""
    <html>
    <head>
      <title>注册 - BiliObjCLint</title>
      {STYLE}
      {REGISTER_STYLE}
    </head>
    <body>
      <div class="register-page">
        <div class="register-card">
          <img class="register-logo" src="/static/biliobjclint_logo.png" alt="BiliObjCLint" />
          <h2>创建账号</h2>
          <p class="subtitle">注册后即可使用 Dashboard</p>
          {err}
          {succ}
          <form method="post" action="/register">
            <div class="form-group">
              <label>用户名</label>
              <input name="username" placeholder="请输入用户名" autocomplete="username" required minlength="3" maxlength="32" />
              <p class="hint">3-32 个字符，支持字母、数字、下划线</p>
            </div>
            <div class="form-group">
              <label>密码</label>
              <input name="password" type="password" placeholder="请输入密码" autocomplete="new-password" required minlength="6" />
              <p class="hint">至少 6 个字符</p>
            </div>
            <div class="form-group">
              <label>确认密码</label>
              <input name="confirm_password" type="password" placeholder="请再次输入密码" autocomplete="new-password" required />
            </div>
            <button type="submit" class="submit-btn">注 册</button>
          </form>
          <p class="login-link">已有账号？<a href="/login">立即登录</a></p>
        </div>
      </div>
    </body>
    </html>
    """
