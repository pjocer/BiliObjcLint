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

.login-card .form-group input[type="text"],
.login-card .form-group input[type="password"] {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid #e6ded4;
  border-radius: 10px;
  font-size: 15px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.login-card .form-group input:focus {
  outline: none;
  border-color: #fb7299;
  box-shadow: 0 0 0 3px rgba(251, 114, 153, 0.15);
}

.login-card .remember-row {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 4px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #6b6b6b;
  cursor: pointer;
  text-align: left;
  padding-left: 14px;  /* 与输入框内边距对齐 */
}

.login-card .remember-row input[type="checkbox"] {
  width: 14px;
  height: 14px;
  margin: 0;
  accent-color: #fb7299;
  cursor: pointer;
  flex-shrink: 0;
}

.login-card .remember-row label {
  margin: 0;
  cursor: pointer;
  line-height: 1;
}

.login-card .submit-btn {
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

.login-card .submit-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(251, 114, 153, 0.4);
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

.login-card .register-link {
  margin-top: 20px;
  font-size: 14px;
  color: #6b6b6b;
}

.login-card .register-link a {
  color: #fb7299;
  text-decoration: none;
  font-weight: 600;
}

.login-card .register-link a:hover {
  text-decoration: underline;
}

.login-card .success {
  background: #f0fdf4;
  color: #166534;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 16px;
  text-align: left;
}
</style>
"""

LOGIN_SCRIPT = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('login-form');
    const usernameInput = document.getElementById('username');
    const rememberCheckbox = document.getElementById('remember');

    // 页面加载时：检查是否有保存的用户名
    const savedUsername = localStorage.getItem('biliobjclint_username');
    if (savedUsername) {
        usernameInput.value = savedUsername;
        rememberCheckbox.checked = true;
        // 聚焦到密码框
        document.getElementById('password').focus();
    }

    // 表单提交时：根据"记住密码"选项保存或清除用户名
    form.addEventListener('submit', function() {
        if (rememberCheckbox.checked) {
            localStorage.setItem('biliobjclint_username', usernameInput.value);
        } else {
            localStorage.removeItem('biliobjclint_username');
        }
    });
});
</script>
"""


def render_login(error: str = "", success: str = "") -> str:
    """Render the login page."""
    err = f'<div class="error">{error}</div>' if error else ""
    succ = f'<div class="success">{success}</div>' if success else ""
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
          {succ}
          {err}
          <form id="login-form" method="post" action="/login" autocomplete="on">
            <div class="form-group">
              <label for="username">用户名</label>
              <input type="text" id="username" name="username" placeholder="请输入用户名" autocomplete="username" />
            </div>
            <div class="form-group">
              <label for="password">密码</label>
              <input type="password" id="password" name="password" placeholder="请输入密码" autocomplete="current-password" />
            </div>
            <div class="remember-row">
              <input type="checkbox" name="remember" value="1" id="remember" />
              <label for="remember">记住密码</label>
            </div>
            <button type="submit" class="submit-btn">登 录</button>
          </form>
          <p class="register-link">还没有账号？<a href="/register">立即注册</a></p>
        </div>
      </div>
      {LOGIN_SCRIPT}
    </body>
    </html>
    """
