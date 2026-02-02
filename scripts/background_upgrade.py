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


def get_changelog_for_version(version: str) -> str:
    """获取指定版本的 CHANGELOG（仅保留 bullet points，去除 markdown 标题）"""
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
                changelog_lines = []
                search_pattern = f'## v{version}'
                logger.info(f"Searching for pattern: {search_pattern}")
                for line in lines:
                    if line.startswith(f'## v{version}') or line.startswith(f'## [{version}'):
                        in_version = True
                        logger.info(f"Found version header: {line}")
                        continue
                    elif line.startswith('## ') and in_version:
                        break
                    elif in_version:
                        # 只保留 bullet points (- 开头的行)，跳过 ### 标题和空行
                        stripped = line.strip()
                        if stripped.startswith('- '):
                            changelog_lines.append(stripped)
                if changelog_lines:
                    result = '\n'.join(changelog_lines)
                    logger.info(f"Found changelog content, length: {len(result)}")
                    return result
                else:
                    logger.info("No changelog content found for this version")
            else:
                logger.info("Changelog file does not exist")
        else:
            logger.info("brew_prefix is None")
    except Exception as e:
        logger.exception(f"Failed to get changelog: {e}")
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


def update_build_phase(
    project_path: str,
    target_name: Optional[str] = None,
    project_name: Optional[str] = None,
    scripts_dir: Optional[str] = None
) -> bool:
    """
    更新 Build Phase 到最新版本（使用当前脚本路径）

    Args:
        project_path: Xcode 项目路径
        target_name: Target 名称
        project_name: 项目名称（用于 workspace）
        scripts_dir: scripts 目录路径

    Returns:
        是否成功
    """
    try:
        import os
        from xcode_integrator import XcodeIntegrator, SCRIPT_VERSION

        brew_prefix = get_brew_prefix()
        lint_path = str(brew_prefix / 'libexec') if brew_prefix else str(SCRIPT_DIR.parent)

        integrator = XcodeIntegrator(project_path, lint_path, project_name)

        if not integrator.load_project():
            logger.error("Failed to load project")
            return False

        target = integrator.get_target(target_name)
        if not target:
            logger.error(f"Target not found: {target_name}")
            return False

        current_version = None
        if integrator.has_lint_phase(target):
            current_version = integrator.get_lint_phase_version(target)
            if current_version == SCRIPT_VERSION:
                logger.info(f"Build Phase already at version {SCRIPT_VERSION}")
                return True

        # 计算 scripts_path 相对于 SRCROOT 的路径
        srcroot = integrator.get_project_srcroot()
        if srcroot and scripts_dir:
            relative_path = os.path.relpath(scripts_dir, srcroot)
            scripts_path_in_phase = "${SRCROOT}/" + relative_path
        else:
            scripts_path_in_phase = "${SRCROOT}/../scripts"

        # 更新 Build Phase
        success = integrator.add_lint_phase(
            target,
            dry_run=False,
            override=True,
            scripts_path=scripts_path_in_phase
        )

        if success:
            integrator.save()
            logger.info(f"Build Phase updated: {current_version} -> {SCRIPT_VERSION}")

        return success

    except Exception as e:
        logger.exception(f"Failed to update build phase: {e}")
        return False


def update_build_phase_with_new_version(
    project_path: str,
    target_name: Optional[str] = None,
    project_name: Optional[str] = None,
    scripts_dir: Optional[str] = None,
    new_version: Optional[str] = None
) -> bool:
    """
    更新 Build Phase 到最新版本（从新版本的 brew prefix 导入模块）

    关键：brew upgrade 完成后，需要从新安装的路径导入 xcode_integrator，
    而不是从当前运行脚本的路径（旧版本）导入。

    Args:
        project_path: Xcode 项目路径
        target_name: Target 名称
        project_name: 项目名称（用于 workspace）
        scripts_dir: scripts 目录路径
        new_version: 新版本号

    Returns:
        是否成功
    """
    try:
        import os
        import importlib.util

        # 获取新版本的 brew prefix
        brew_prefix = get_brew_prefix()
        if not brew_prefix:
            logger.error("Cannot get brew prefix for new version")
            return False

        new_scripts_path = brew_prefix / 'libexec' / 'scripts'
        logger.info(f"Loading xcode_integrator from new version: {new_scripts_path}")

        # 从新版本路径动态导入 xcode_integrator
        xcode_integrator_path = new_scripts_path / 'xcode_integrator.py'
        if not xcode_integrator_path.exists():
            logger.error(f"xcode_integrator.py not found at {xcode_integrator_path}")
            return False

        spec = importlib.util.spec_from_file_location("xcode_integrator_new", xcode_integrator_path)
        xcode_integrator_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(xcode_integrator_module)

        XcodeIntegrator = xcode_integrator_module.XcodeIntegrator
        SCRIPT_VERSION = xcode_integrator_module.SCRIPT_VERSION

        logger.info(f"Loaded SCRIPT_VERSION from new version: {SCRIPT_VERSION}")

        lint_path = str(brew_prefix / 'libexec')
        integrator = XcodeIntegrator(project_path, lint_path, project_name)

        if not integrator.load_project():
            logger.error("Failed to load project")
            return False

        target = integrator.get_target(target_name)
        if not target:
            logger.error(f"Target not found: {target_name}")
            return False

        current_version = None
        if integrator.has_lint_phase(target):
            current_version = integrator.get_lint_phase_version(target)
            logger.info(f"Current Build Phase version: {current_version}")

        # 计算 scripts_path 相对于 SRCROOT 的路径
        srcroot = integrator.get_project_srcroot()
        if srcroot and scripts_dir:
            relative_path = os.path.relpath(scripts_dir, srcroot)
            scripts_path_in_phase = "${SRCROOT}/" + relative_path
        else:
            scripts_path_in_phase = "${SRCROOT}/../scripts"

        # 更新 Build Phase
        success = integrator.add_lint_phase(
            target,
            dry_run=False,
            override=True,
            scripts_path=scripts_path_in_phase
        )

        if success:
            integrator.save()
            logger.info(f"Build Phase updated: {current_version} -> {SCRIPT_VERSION}")

        return success

    except Exception as e:
        logger.exception(f"Failed to update build phase with new version: {e}")
        return False


def show_updating_notification():
    """显示正在更新的系统通知"""
    title = "BiliObjCLint"
    message = "检测到BiliObjcLint需要更新，正在后台更新中..."
    try:
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(['osascript', '-e', script], capture_output=True, timeout=10)
    except Exception as e:
        logger.debug(f"Failed to show updating notification: {e}")


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
        # 重要：使用新版本的 brew prefix 路径，而不是当前脚本的路径
        if project_path:
            logger.info("Force updating Build Phase...")
            update_build_phase_with_new_version(
                project_path, target_name, project_name, scripts_dir, remote_ver
            )

        # 6. 获取 CHANGELOG 内容（从新版本读取）
        logger.info(f"Getting changelog for version {remote_ver}...")
        changelog = get_changelog_for_version(remote_ver)
        logger.info(f"Changelog content length: {len(changelog)}")

        # 7. 显示更新完成弹窗（阻塞等待用户点击 OK）
        logger.info("Showing update dialog...")
        show_update_dialog(remote_ver, changelog)

        # 8. 用户点击 OK 后，进程正常结束
        logger.info("User acknowledged update, process ending")
        return True

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
