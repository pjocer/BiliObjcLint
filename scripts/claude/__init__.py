"""
Claude Fixer 包

自动修复 Objective-C 代码问题的 Claude 集成模块

主要组件:
- ClaudeFixer: 主修复器类
- HtmlReportGenerator: HTML 报告生成器
- build_fix_prompt: Prompt 构建函数
"""
import sys
from pathlib import Path

# 添加 scripts 目录到路径以支持绝对导入
_SCRIPT_DIR = Path(__file__).parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from claude.fixer import ClaudeFixer
from claude.html_report import HtmlReportGenerator, open_html_report
from claude.prompt_builder import build_fix_prompt
from claude.dialogs import show_dialog, show_progress_notification
from claude.cli import main, load_config, load_violations

__all__ = [
    'ClaudeFixer',
    'HtmlReportGenerator',
    'open_html_report',
    'build_fix_prompt',
    'show_dialog',
    'show_progress_notification',
    'main',
    'load_config',
    'load_violations',
]
