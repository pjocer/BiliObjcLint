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


class DialogError(RuntimeError):
    """macOS 对话框调用失败。"""


def _escape_applescript_string(value: str) -> str:
    """转义 AppleScript 字符串。"""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _format_applescript_message(message: str) -> str:
    """将多行消息转换为 AppleScript 字符串表达式。"""
    normalized = message.replace('\r\n', '\n').replace('\r', '\n')
    return '" & return & "'.join(
        _escape_applescript_string(part)
        for part in normalized.split('\n')
    )


def show_dialog(title: str, message: str, buttons: List[str],
                default_button: str = None, icon: str = "caution",
                raise_on_error: bool = False) -> Optional[str]:
    """
    显示 macOS 原生对话框

    Args:
        title: 对话框标题
        message: 消息内容
        buttons: 按钮列表
        default_button: 默认按钮
        icon: 图标类型 (stop, note, caution)
        raise_on_error: 显示失败时是否抛出异常

    Returns:
        用户点击的按钮名称，如果取消则返回 None
    """
    if not buttons:
        raise ValueError("buttons must not be empty")

    if default_button is None:
        default_button = buttons[-1]

    buttons_str = ', '.join(f'"{_escape_applescript_string(b)}"' for b in buttons)
    escaped_default_button = _escape_applescript_string(default_button)
    escaped_title = _escape_applescript_string(title)

    # 处理消息中的换行符，使用 AppleScript 的 return 关键字
    escaped_message = _format_applescript_message(message)

    script = (
        'tell current application\n'
        'activate\n'
        f'display dialog "{escaped_message}" '
        f'buttons {{{buttons_str}}} '
        f'default button "{escaped_default_button}" '
        f'with title "{escaped_title}" with icon {icon}\n'
        'end tell'
    )

    try:
        logger.debug(f"Showing dialog: {title}")
        logger.debug(f"AppleScript: {script}")
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=30
        )
        logger.debug(f"Dialog result: returncode={result.returncode}, stdout={result.stdout}, stderr={result.stderr}")
        if result.returncode == 0:
            # 解析返回值，格式为 "button returned:按钮名"
            output = result.stdout.strip()
            if 'button returned:' in output:
                return output.split('button returned:')[1].strip()
            error_msg = "Dialog returned successfully but no button result was found"
        else:
            error_output = result.stderr.strip() or result.stdout.strip() or f"osascript exit code {result.returncode}"
            if 'User canceled' in error_output or '用户已取消' in error_output or '(-128)' in error_output:
                logger.info(f"Dialog cancelled by user: {error_output}")
                return None
            error_msg = f"Dialog AppleScript failed: {error_output}"

        logger.error(error_msg)
        if raise_on_error:
            raise DialogError(error_msg)
        return None
    except Exception as e:
        logger.exception(f"Dialog exception: {e}")
        if raise_on_error:
            raise DialogError(str(e)) from e
        return None


def show_progress_notification(message: str) -> subprocess.Popen:
    """
    显示进度通知（非阻塞的通知横幅）

    Returns:
        进程对象，可用于后续关闭
    """
    script = f'''
    display notification "{_escape_applescript_string(message)}" with title "BiliObjCLint" subtitle "Claude 自动修复"
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
    escaped_message = _format_applescript_message(message)
    script = f'''
    tell current application
        activate
        display dialog "{escaped_message}" buttons {{"请稍候..."}} default button 1 with title "BiliObjCLint - Claude 修复中" with icon note giving up after 300
    end tell
    '''
    return subprocess.Popen(
        ['osascript', '-e', script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
