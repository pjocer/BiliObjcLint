"""
Claude Fixer - macOS 对话框模块

提供 macOS 原生对话框和通知功能
"""
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# 添加 scripts 目录到路径以支持绝对导入
_SCRIPT_DIR = Path(__file__).parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from core.lint.logger import get_logger

logger = get_logger("claude_fix")


def show_dialog(title: str, message: str, buttons: List[str],
                default_button: str = None, icon: str = "caution") -> Optional[str]:
    """
    显示 macOS 原生对话框

    Args:
        title: 对话框标题
        message: 消息内容
        buttons: 按钮列表
        default_button: 默认按钮
        icon: 图标类型 (stop, note, caution)

    Returns:
        用户点击的按钮名称，如果取消则返回 None
    """
    if default_button is None:
        default_button = buttons[-1]

    buttons_str = ', '.join(f'"{b}"' for b in buttons)

    # 处理消息中的换行符，使用 AppleScript 的 return 关键字
    # AppleScript 不支持 \ 续行符，必须在单行中构建
    escaped_message = message.replace('\n', '" & return & "')

    # 构建单行 AppleScript 命令（AppleScript 不支持 \ 续行符）
    script = f'display dialog "{escaped_message}" buttons {{{buttons_str}}} default button "{default_button}" with title "{title}" with icon {icon}'

    try:
        logger.debug(f"Showing dialog: {title}")
        logger.debug(f"AppleScript: {script}")
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True
        )
        logger.debug(f"Dialog result: returncode={result.returncode}, stdout={result.stdout}, stderr={result.stderr}")
        if result.returncode == 0:
            # 解析返回值，格式为 "button returned:按钮名"
            output = result.stdout.strip()
            if 'button returned:' in output:
                return output.split('button returned:')[1].strip()
        return None
    except Exception as e:
        logger.exception(f"Dialog exception: {e}")
        return None


def show_progress_notification(message: str) -> subprocess.Popen:
    """
    显示进度通知（非阻塞的通知横幅）

    Returns:
        进程对象，可用于后续关闭
    """
    script = f'''
    display notification "{message}" with title "BiliObjCLint" subtitle "Claude 自动修复"
    '''
    return subprocess.Popen(
        ['osascript', '-e', script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def show_progress_dialog(message: str) -> subprocess.Popen:
    """
    显示进度对话框（带进度指示的对话框）

    使用 AppleScript 的 progress 特性显示一个模态进度窗口

    Returns:
        进程对象
    """
    # 使用一个简单的弹窗来显示进度状态
    # 注意：真正的进度条需要 Cocoa 应用，这里使用简化方案
    script = f'''
    tell application "System Events"
        display dialog "{message}" \\
            buttons {{"请稍候..."}} \\
            default button 1 \\
            with title "BiliObjCLint - Claude 修复中" \\
            with icon note \\
            giving up after 300
    end tell
    '''
    return subprocess.Popen(
        ['osascript', '-e', script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
