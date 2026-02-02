#!/usr/bin/env python3
"""
BiliObjCLint 后台升级脚本

由 check_update.py 的 background_upgrade() 函数调用，在独立进程中执行：
1. brew update
2. brew upgrade biliobjclint
3. 更新成功后复制脚本到目标工程
4. 显示更新完成弹窗

Usage:
    python3 background_upgrade.py --local-ver 1.1.28 --remote-ver 1.1.29 [--scripts-dir /path/to/scripts]
"""
import argparse
import subprocess
import shutil
import stat
import sys
from pathlib import Path
from typing import Optional

# 添加 scripts 目录到路径以导入 logger
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from core.logger import get_logger
    logger = get_logger("background_upgrade")
except Exception:
    # 如果导入失败，使用简单的打印日志
    class DummyLogger:
        def info(self, msg): print(f"[INFO] {msg}")
        def error(self, msg): print(f"[ERROR] {msg}")
        def debug(self, msg): pass
        def exception(self, msg): print(f"[EXCEPTION] {msg}")
    logger = DummyLogger()


def get_brew_prefix() -> Optional[Path]:
    """获取 biliobjclint 的 brew 安装路径"""
    try:
        result = subprocess.run(
            ['brew', '--prefix', 'biliobjclint'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception as e:
        logger.debug(f"Failed to get brew prefix: {e}")
    return None


def get_changelog_for_version(version: str) -> str:
    """获取指定版本的 CHANGELOG"""
    try:
        brew_prefix = get_brew_prefix()
        if brew_prefix:
            changelog_file = brew_prefix / 'libexec' / 'CHANGELOG.md'
            if changelog_file.exists():
                content = changelog_file.read_text()
                lines = content.split('\n')
                in_version = False
                changelog_lines = []
                for line in lines:
                    if line.startswith(f'## v{version}') or line.startswith(f'## [{version}'):
                        in_version = True
                        continue
                    elif line.startswith('## ') and in_version:
                        break
                    elif in_version:
                        changelog_lines.append(line)
                if changelog_lines:
                    return '\n'.join(changelog_lines).strip()
    except Exception as e:
        logger.debug(f"Failed to get changelog: {e}")
    return ""


def show_update_dialog(version: str, changelog: str):
    """显示更新完成弹窗"""
    title = f"BiliObjCLint 已更新到 v{version}"
    message = "更新完成！"
    if changelog:
        message += f"\n\n更新内容:\n{changelog[:500]}"
    try:
        # 转义双引号
        message = message.replace('"', '\\"')
        script = f'display dialog "{message}" with title "{title}" buttons {{"OK"}} default button "OK"'
        subprocess.run(['osascript', '-e', script], capture_output=True, timeout=30)
    except Exception as e:
        logger.debug(f"Failed to show dialog: {e}")


def copy_scripts_to_project(scripts_dir: Path, force: bool = False) -> bool:
    """
    复制 bootstrap.sh 和 code_style_check.sh 到目标工程

    Args:
        scripts_dir: 目标 scripts 目录
        force: 是否强制覆盖

    Returns:
        是否成功
    """
    brew_prefix = get_brew_prefix()
    if not brew_prefix:
        logger.error("Cannot get brew prefix")
        return False

    scripts_dir.mkdir(parents=True, exist_ok=True)

    success = True
    for script_name in ['bootstrap.sh', 'code_style_check.sh']:
        source = brew_prefix / 'libexec' / 'config' / script_name
        target = scripts_dir / script_name

        if not source.exists():
            logger.error(f"Source script not found: {source}")
            success = False
            continue

        if target.exists() and not force:
            logger.info(f"Script already exists: {target}")
            continue

        try:
            shutil.copy2(source, target)
            # 设置执行权限
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            logger.info(f"Copied {script_name} to {target}")
        except Exception as e:
            logger.exception(f"Failed to copy {script_name}: {e}")
            success = False

    return success


def do_upgrade(local_ver: str, remote_ver: str, scripts_dir: Optional[str] = None) -> bool:
    """
    执行 brew upgrade

    Args:
        local_ver: 当前本地版本
        remote_ver: 远端最新版本
        scripts_dir: 目标工程 scripts 目录路径

    Returns:
        是否成功
    """
    logger.info(f"Starting background upgrade: {local_ver} -> {remote_ver}")

    try:
        # 1. brew update
        logger.info("Running brew update...")
        result = subprocess.run(['brew', 'update'], capture_output=True, timeout=120)
        if result.returncode != 0:
            logger.error(f"brew update failed: {result.stderr}")
            # 继续执行 upgrade，update 失败不阻塞

        # 2. brew upgrade
        logger.info("Running brew upgrade biliobjclint...")
        result = subprocess.run(
            ['brew', 'upgrade', 'biliobjclint'],
            capture_output=True, timeout=300
        )

        if result.returncode == 0:
            logger.info("Upgrade completed successfully")

            # 3. 强制覆盖脚本到目标工程
            if scripts_dir:
                copy_scripts_to_project(Path(scripts_dir), force=True)

            # 4. 显示弹窗
            changelog = get_changelog_for_version(remote_ver)
            show_update_dialog(remote_ver, changelog)

            return True
        else:
            stderr = result.stderr.decode() if isinstance(result.stderr, bytes) else result.stderr
            # 如果已经是最新版本，不算错误
            if 'already installed' in stderr or 'already the newest' in stderr.lower():
                logger.info("Already up to date")
                return True
            logger.error(f"brew upgrade failed: {stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Upgrade timed out")
        return False
    except Exception as e:
        logger.exception(f"Upgrade failed: {e}")
        return False


def parse_args():
    parser = argparse.ArgumentParser(
        description='BiliObjCLint 后台升级脚本'
    )

    parser.add_argument(
        '--local-ver',
        required=True,
        help='当前本地版本'
    )

    parser.add_argument(
        '--remote-ver',
        required=True,
        help='远端最新版本'
    )

    parser.add_argument(
        '--scripts-dir',
        default=None,
        help='目标工程 scripts 目录路径'
    )

    return parser.parse_args()


def main():
    args = parse_args()

    logger.info(f"Background upgrade started: {args.local_ver} -> {args.remote_ver}")
    if args.scripts_dir:
        logger.info(f"Scripts dir: {args.scripts_dir}")

    success = do_upgrade(args.local_ver, args.remote_ver, args.scripts_dir)

    logger.info(f"Background upgrade finished: success={success}")
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
