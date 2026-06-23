"""
BiliObjCLint Brew 工具模块

提供与 Homebrew 交互的工具函数，当前聚焦于 Homebrew 6.0+ 的 tap trust 自动化。

背景：
    Homebrew 6.0.0 起默认要求非官方 tap 显式 trust，否则 `brew info/upgrade <formula>`
    会报 `Refusing to load formula from untrusted tap`，导致升级链路受阻。本模块在
    工具注入目标工程时自动检测并信任 `pjocer/biliobjclint` tap。

设计约束：
    - 只使用标准库（subprocess/json/logging），不依赖 core.lint.logger，保证 upgrader.py
      等自包含模块也能安全导入（升级过程中旧版本可能被删除）。
    - logger 作为可选参数注入，None 时回退到标准 logging。
"""
import json
import logging
import subprocess
from typing import Optional

# 默认信任的 tap
DEFAULT_TAP = "pjocer/biliobjclint"

# 模块级 logger（logger 参数为 None 时使用）
_module_logger = logging.getLogger("biliobjclint.brew_utils")
_module_logger.addHandler(logging.NullHandler())


def _get_logger(logger=None):
    """获取实际使用的 logger。注入优先，否则用模块级标准 logger。"""
    return logger if logger is not None else _module_logger


def is_tap_trusted(tap: str = DEFAULT_TAP, logger=None) -> Optional[bool]:
    """
    检测 brew tap 是否已被信任。

    用 `brew trust --json v1` 解析已信任条目，检查 tap 是否在 taps 列表中。

    Args:
        tap: tap 名称，如 "pjocer/biliobjclint"
        logger: 可选日志记录器

    Returns:
        True  - tap 已被信任
        False - tap 未被信任
        None  - 无法检测（brew < 6.0 无 trust 命令，或 brew 不可用）→ 调用方应跳过
    """
    log = _get_logger(logger)
    try:
        result = subprocess.run(
            ['brew', 'trust', '--json', 'v1'],
            capture_output=True, text=True, timeout=10
        )
    except Exception as e:
        log.debug(f"is_tap_trusted: 调用 brew 失败: {e}")
        return None

    if result.returncode != 0:
        # brew < 6.0 无 trust 子命令，或 brew 异常 → 不需要 trust，跳过
        log.debug(f"is_tap_trusted: brew trust --json 退出码 {result.returncode}，"
                  f"视为 brew < 6.0 或不可用，跳过 trust 检查")
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        log.debug(f"is_tap_trusted: 解析 JSON 失败: {e}")
        return None

    return tap in data.get("taps", [])


def ensure_tap_trusted(
    tap: str = DEFAULT_TAP,
    logger=None,
    dry_run: bool = False
) -> bool:
    """
    确保 brew tap 已被信任。未信任则执行 `brew trust <tap>`。

    Homebrew 6.0+ 默认要求非官方 tap 显式 trust。本函数在注入目标工程时调用，
    自动检测并信任 tap，避免升级链路（brew upgrade）被 untrusted 拦截。

    Args:
        tap: tap 名称，如 "pjocer/biliobjclint"
        logger: 可选日志记录器
        dry_run: 模拟模式，只检测并打印，不执行实际 trust 写操作

    Returns:
        True  - tap 已信任，或无需 trust（brew < 6.0），或 dry_run 模拟完成
        False - trust 执行失败
    """
    log = _get_logger(logger)
    trusted = is_tap_trusted(tap=tap, logger=log)

    if trusted is None:
        log.info(f"跳过 tap trust 检查（brew < 6.0 或 brew 不可用）: {tap}")
        return True

    if trusted:
        log.info(f"tap 已被信任: {tap}")
        return True

    # 未信任
    if dry_run:
        log.info(f"[DRY RUN] 将执行 brew trust {tap}")
        print(f"[BiliObjCLint] [DRY RUN] 将执行 brew trust {tap}")
        return True

    log.info(f"tap 未被信任，正在执行 brew trust {tap} ...")
    print(f"[BiliObjCLint] Homebrew 6.0+ 要求 tap trust，正在信任 tap: {tap}")
    try:
        result = subprocess.run(
            ['brew', 'trust', tap],
            capture_output=True, text=True, timeout=30
        )
    except Exception as e:
        log.error(f"brew trust {tap} 异常: {e}")
        print(f"[BiliObjCLint] brew trust 失败，请手动执行: brew trust {tap}")
        return False

    if result.returncode == 0:
        log.info(f"已信任 tap: {tap}")
        print(f"[BiliObjCLint] 已信任 tap: {tap}")
        return True

    stderr = result.stderr.strip() if result.stderr else ""
    log.error(f"brew trust {tap} 失败 (退出码 {result.returncode}): {stderr}")
    print(f"[BiliObjCLint] brew trust 失败，请手动执行: brew trust {tap}")
    return False
