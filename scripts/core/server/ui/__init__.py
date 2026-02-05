"""UI templates for BiliObjCLint server.

This module re-exports all page rendering functions for backwards compatibility.
The actual implementations are split into separate modules:
- styles.py: Shared CSS styles
- components.py: Reusable UI components (charts, toggles, etc.)
- login.py: Login page
- register.py: Register page
- dashboard.py: Dashboard page
- users.py: User management page
- violations.py: Violations list and detail pages
"""
from __future__ import annotations

# Re-export all public render functions
from .login import render_login
from .register import render_register
from .dashboard import render_dashboard
from .users import render_users
from .violations import render_violations_list, render_violation_detail

# Re-export styles for any direct usage
from .styles import STYLE

# Re-export components for extensibility
from .components import (
    get_rule_display_name,
    render_ios_switch,
    render_rule_name,
    render_trend_chart,
    render_project_option,
)

__all__ = [
    "render_login",
    "render_register",
    "render_dashboard",
    "render_users",
    "render_violations_list",
    "render_violation_detail",
    "STYLE",
    "get_rule_display_name",
    "render_ios_switch",
    "render_rule_name",
    "render_trend_chart",
    "render_project_option",
]
