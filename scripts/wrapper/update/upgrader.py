#!/usr/bin/env python3
"""
BiliObjCLint 后台升级脚本

由 checker.py 的 background_upgrade() 函数调用，在独立进程中执行：
1. brew update
2. brew upgrade biliobjclint
3. 更新成功后复制脚本到目标工程
4. 显示更新完成弹窗

Usage:
    python3 upgrader.py --local-ver 1.1.28 --remote-ver 1.1.29 [--scripts-dir /path/to/scripts]
"""
import argparse
import subprocess
import shutil
import shlex
import stat
import sys
from pathlib import Path
from typing import Optional

import datetime

# 日志文件路径（固定位置，不会被 brew upgrade 删除）
LOG_FILE = Path.home() / '.biliobjclint' / 'background_upgrade.log'


def log_to_file(level: str, msg: str):
    """直接写入日志文件（确保 nohup 能捕获）"""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{ts}] [{level}] {msg}"
    # 同时输出到 stdout（nohup 捕获）和日志文件
    print(log_line, flush=True)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(log_line + '\n')
    except Exception:
        pass


class FileLogger:
    """直接写入文件的 logger，确保日志不会随旧版本被删除"""
    def info(self, msg): log_to_file("INFO", msg)
    def error(self, msg): log_to_file("ERROR", msg)
    def debug(self, msg): log_to_file("DEBUG", msg)
    def exception(self, msg): log_to_file("EXCEPTION", msg)


logger = FileLogger()


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


def get_changelog_for_version(version: str) -> tuple:
    """
    获取指定版本的 CHANGELOG，分离普通内容和重要提示

    Returns:
        tuple: (normal_changelog: str, important_notes: str)
    """
    normal_lines = []
    important_lines = []

    try:
        brew_prefix = get_brew_prefix()
        logger.info(f"Looking for changelog, brew_prefix: {brew_prefix}, version: {version}")
        if brew_prefix:
            # CHANGELOG.md is at Cellar root, not in libexec (Homebrew auto-extracts it)
            changelog_file = brew_prefix / 'CHANGELOG.md'
            logger.info(f"Changelog file path: {changelog_file}, exists: {changelog_file.exists()}")
            if changelog_file.exists():
                content = changelog_file.read_text()
                lines = content.split('\n')
                in_version = False
                in_important = False
                search_pattern = f'## v{version}'
                logger.info(f"Searching for pattern: {search_pattern}")

                for line in lines:
                    if line.startswith(f'## v{version}') or line.startswith(f'## [{version}'):
                        in_version = True
                        logger.info(f"Found version header: {line}")
                        continue
                    elif line.startswith('## ') and in_version:
                        # 遇到下一个版本，结束
                        break
                    elif in_version:
                        stripped = line.strip()
                        # 检测 ### 重要 段落
                        if stripped == '### 重要':
                            in_important = True
                            continue
                        elif stripped.startswith('### ') and in_important:
                            in_important = False

                        # 只保留 bullet points (- 开头的行)
                        if stripped.startswith('- '):
                            if in_important:
                                important_lines.append(stripped)
                            else:
                                normal_lines.append(stripped)

                normal_result = '\n'.join(normal_lines) if normal_lines else ""
                important_result = '\n'.join(important_lines) if important_lines else ""

                logger.info(f"Found changelog: normal={len(normal_result)}, important={len(important_result)}")
                return normal_result, important_result
            else:
                logger.info("Changelog file does not exist")
        else:
            logger.info("brew_prefix is None")
    except Exception as e:
        logger.exception(f"Failed to get changelog: {e}")

    return "", ""


def show_update_dialog(version: str, changelog: str, important: str = ""):
    """
    显示更新完成弹窗

    Args:
        version: 版本号
        changelog: 普通更新内容
        important: 重要提示内容（用 emoji 高亮显示）
    """
    title = f"BiliObjCLint 已更新到 v{version}"
    message = "更新完成！"

    if changelog:
        message += f"\n\n更新内容:\n{changelog[:400]}"

    if important:
        message += f"\n\n━━━━━━━━━━━━━━━━━━━━\n⚠️ 重要提示 ⚠️\n━━━━━━━━━━━━━━━━━━━━\n{important}"

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


def show_updating_notification():
    """显示正在更新的系统通知"""
    title = "BiliObjCLint"
    message = "检测到BiliObjcLint需要更新，正在后台更新中..."
    try:
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(['osascript', '-e', script], capture_output=True, timeout=10)
    except Exception as e:
        logger.debug(f"Failed to show updating notification: {e}")


def _update_build_phase_subprocess(
    project_path: str,
    target_name: Optional[str] = None,
    project_name: Optional[str] = None,
    scripts_dir: Optional[str] = None,
    new_version: Optional[str] = None
) -> bool:
    """
    使用子进程调用 phase_updater.py 更新 Build Phase

    这是解决模块缓存问题的终极方案：
    - 当前脚本从旧版本运行，进程中已加载旧版本模块
    - 使用子进程启动新版本的 Python，完全隔离环境
    - 在纯净的新版本环境中执行 Build Phase 更新
    """
    try:
        brew_prefix = get_brew_prefix()
        if not brew_prefix:
            logger.error("Cannot get brew prefix for subprocess")
            return False

        # 新版本的 Python 环境
        new_python = brew_prefix / 'libexec' / '.venv' / 'bin' / 'python3'
        if not new_python.exists():
            logger.error(f"New Python not found: {new_python}")
            return False

        # 新版本的 phase_updater.py 脚本
        phase_updater = brew_prefix / 'libexec' / 'scripts' / 'wrapper' / 'update' / 'phase_updater.py'
        if not phase_updater.exists():
            logger.error(f"phase_updater.py not found: {phase_updater}")
            return False

        # 构建命令行参数
        args = [str(new_python), str(phase_updater)]
        args.extend(['--project-path', project_path])
        if target_name:
            args.extend(['--target-name', target_name])
        if project_name:
            args.extend(['--project-name', project_name])
        if scripts_dir:
            args.extend(['--scripts-dir', scripts_dir])

        logger.info(f"Running Build Phase update: {' '.join(args)}")

        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=60
        )

        # 记录输出
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                logger.info(f"[phase_updater] {line}")
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                logger.error(f"[phase_updater] {line}")

        if result.returncode != 0:
            logger.error(f"phase_updater failed with return code: {result.returncode}")
            return False

        logger.info("Build Phase updated successfully via phase_updater.py")
        return True

    except subprocess.TimeoutExpired:
        logger.error("Build Phase update subprocess timed out")
        return False
    except Exception as e:
        logger.exception(f"Failed to update build phase via subprocess: {e}")
        return False


def do_upgrade(
    local_ver: str,
    remote_ver: str,
    scripts_dir: Optional[str] = None,
    project_path: Optional[str] = None,
    target_name: Optional[str] = None,
    project_name: Optional[str] = None
) -> bool:
    """
    执行 brew upgrade

    流程：
    1. 显示系统通知 "检测到BiliObjcLint需要更新，正在后台更新中..."
    2. brew update
    3. brew upgrade biliobjclint（同步执行）
    4. 复制脚本到目标工程
    5. 强制更新 Build Phase（使用新版本的脚本）
    6. 获取 CHANGELOG 内容
    7. 显示更新完成弹窗
    8. 用户点击 OK 后进程结束

    Args:
        local_ver: 当前本地版本
        remote_ver: 远端最新版本
        scripts_dir: 目标工程 scripts 目录路径
        project_path: Xcode 项目路径
        target_name: Target 名称
        project_name: 项目名称

    Returns:
        是否成功
    """
    logger.info(f"Starting background upgrade: {local_ver} -> {remote_ver}")

    try:
        # 1. 先显示系统通知（让用户立即知道正在更新）
        logger.info("Showing updating notification...")
        show_updating_notification()

        # 2. brew update
        logger.info("Running brew update...")
        result = subprocess.run(['brew', 'update'], capture_output=True, timeout=120)
        if result.returncode != 0:
            stderr = result.stderr.decode() if isinstance(result.stderr, bytes) else result.stderr
            logger.error(f"brew update failed: {stderr}")
            # 继续执行 upgrade，update 失败不阻塞

        # 3. brew upgrade（同步执行）
        logger.info("Running brew upgrade biliobjclint...")
        result = subprocess.run(
            ['brew', 'upgrade', 'biliobjclint'],
            capture_output=True, timeout=300
        )

        if result.returncode != 0:
            stderr = result.stderr.decode() if isinstance(result.stderr, bytes) else result.stderr
            # 如果已经是最新版本，不算错误
            if 'already installed' in stderr or 'already the newest' in stderr.lower():
                logger.info("Already up to date")
            else:
                logger.error(f"brew upgrade failed: {stderr}")
                return False

        logger.info("Upgrade completed successfully")

        # 4. 复制脚本到目标工程（强制覆盖）
        if scripts_dir:
            logger.info(f"Copying scripts to {scripts_dir}...")
            copy_scripts_to_project(Path(scripts_dir), force=True)

        # 5. 强制更新 Build Phase
        # 【关键】使用子进程调用 phase_updater.py，彻底避免旧版本模块缓存问题
        # 原因：当前脚本从旧版本运行，sys.modules 中缓存了旧版本模块
        #       即使清除缓存，Python 内部状态仍可能有问题
        #       使用子进程完全隔离，确保在纯净的新版本环境中执行
        if project_path:
            logger.info("Force updating Build Phase via subprocess...")
            _update_build_phase_subprocess(
                project_path, target_name, project_name, scripts_dir, remote_ver
            )

        # 6. 获取 CHANGELOG 内容（从新版本读取）
        logger.info(f"Getting changelog for version {remote_ver}...")
        changelog, important = get_changelog_for_version(remote_ver)
        logger.info(f"Changelog content: normal={len(changelog)}, important={len(important)}")

        # 7. 显示更新完成弹窗（阻塞等待用户点击 OK）
        logger.info("Showing update dialog...")
        show_update_dialog(remote_ver, changelog, important)

        # 8. 用户点击 OK 后，进程正常结束
        logger.info("User acknowledged update, process ending")
        return True

    except subprocess.TimeoutExpired:
        logger.error("Upgrade timed out")
        return False
    except Exception as e:
        logger.exception(f"Upgrade failed: {e}")
        return False


def start_background_upgrade(
    local_ver: str,
    remote_ver: str,
    scripts_dir: Optional[Path] = None,
    project_path: Optional[str] = None,
    target_name: Optional[str] = None,
    project_name: Optional[str] = None
):
    """
    启动后台升级进程

    使用独立子进程执行更新，确保主进程退出后更新仍能继续。
    此函数被 checker.py 调用。
    """
    # 添加 scripts 目录到路径
    SCRIPT_DIR = Path(__file__).parent
    SCRIPTS_ROOT = SCRIPT_DIR.parent.parent
    sys.path.insert(0, str(SCRIPTS_ROOT))

    from core.lint.logger import get_logger
    log = get_logger("check_update")

    log.info(f"Starting background upgrade: {local_ver} -> {remote_ver}")

    # 构建命令参数
    upgrade_script = Path(__file__)
    args = [
        '--local-ver', local_ver,
        '--remote-ver', remote_ver,
    ]
    if scripts_dir:
        args.extend(['--scripts-dir', str(scripts_dir)])
    if project_path:
        args.extend(['--project-path', project_path])
    if target_name:
        args.extend(['--target-name', target_name])
    if project_name:
        args.extend(['--project-name', project_name])

    try:
        # 创建日志目录
        log_dir = Path.home() / '.biliobjclint'
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / 'background_upgrade.log'

        # 清空旧日志，写入调试信息
        debug_info = f"""=== Background upgrade started: {local_ver} -> {remote_ver} ===
scripts_dir: {scripts_dir}
project_path: {project_path}
target_name: {target_name}
project_name: {project_name}
"""
        log_file.write_text(debug_info)

        # 获取 venv Python 路径
        brew_prefix = get_brew_prefix()
        if brew_prefix:
            venv_python = brew_prefix / 'libexec' / '.venv' / 'bin' / 'python3'
            if venv_python.exists():
                python_path = str(venv_python)
            else:
                python_path = 'python3'
                log.info(f"Venv python not found at {venv_python}, using system python3")
        else:
            python_path = 'python3'
            log.info("brew prefix not found, using system python3")

        # 使用 shell 命令启动后台进程
        args_quoted = ' '.join(shlex.quote(arg) for arg in args)
        script_path = shlex.quote(str(upgrade_script))
        log_path = shlex.quote(str(log_file))
        python_quoted = shlex.quote(python_path)
        shell_cmd = f'nohup {python_quoted} {script_path} {args_quoted} >> {log_path} 2>&1 &'

        # 将 shell 命令也写入日志文件
        with open(log_file, 'a') as f:
            f.write(f"shell_cmd: {shell_cmd}\n")
            f.write("---\n")

        log.info(f"Shell command: {shell_cmd}")

        subprocess.Popen(
            shell_cmd,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        log.info(f"Background upgrade process started, log: {log_file}")
    except Exception as e:
        log.exception(f"Failed to start background upgrade: {e}")


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

    parser.add_argument(
        '--project-path',
        default=None,
        help='Xcode 项目路径'
    )

    parser.add_argument(
        '--target-name',
        default=None,
        help='Target 名称'
    )

    parser.add_argument(
        '--project-name',
        default=None,
        help='项目名称（用于 workspace）'
    )

    return parser.parse_args()


def main():
    args = parse_args()

    logger.info(f"Background upgrade started: {args.local_ver} -> {args.remote_ver}")
    if args.scripts_dir:
        logger.info(f"Scripts dir: {args.scripts_dir}")
    if args.project_path:
        logger.info(f"Project path: {args.project_path}")
    if args.target_name:
        logger.info(f"Target name: {args.target_name}")

    success = do_upgrade(
        args.local_ver,
        args.remote_ver,
        args.scripts_dir,
        args.project_path,
        args.target_name,
        args.project_name
    )

    logger.info(f"Background upgrade finished: success={success}")
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
