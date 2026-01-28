#!/usr/bin/env python3
"""
Claude 自动修复模块 - 重定向入口

功能：
- 检测 Claude Code CLI 是否可用
- 显示 macOS 原生对话框
- 调用 Claude Code 修复代码违规

本文件为兼容性入口，实际实现已迁移到 scripts/claude/ 模块

Usage:
    python3 claude_fixer.py --violations <file> --config <config> --project-root <path>
"""
import sys
from pathlib import Path

# 添加 scripts 目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# 从新模块导入所有公开接口（保持向后兼容）
from claude import (
    ClaudeFixer,
    HtmlReportGenerator,
    open_html_report,
    build_fix_prompt,
    show_dialog,
    show_progress_notification,
    main,
    load_config,
    load_violations,
)

# 导出 HTTP 服务器相关（供高级用法）
from claude.http_server import ActionRequestHandler

# 导出工具函数（供高级用法）
from claude.utils import escape_html, highlight_objc, read_code_context, cleanup_temp_files


if __name__ == '__main__':
    main()
