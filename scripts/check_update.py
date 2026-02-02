#!/usr/bin/env python3
"""
BiliObjCLint 版本更新检查模块

负责：
1. 检查版本更新（GitHub API vs 本地）
2. 后台执行 brew update && brew upgrade
3. 更新后强制覆盖脚本到目标工程
4. 检查并注入 Code Style Check Build Phase

由 bootstrap.sh 在每次编译时调用
"""
import argparse
import os
import sys
import subprocess
import json
import shutil
import shlex
import stat
from pathlib import Path
from typing import Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError

# 添加 scripts 目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from core.logger import get_logger

# GitHub 仓库信息
GITHUB_REPO = "pjocer/BiliObjcLint"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/tags"

logger = get_logger("check_update")


def get_local_version() -> Optional[str]:
    """从本地 VERSION 文件读取版本号"""
    # 尝试从 brew prefix 读取
    try:
        result = subprocess.run(
            ['brew', '--prefix', 'biliobjclint'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            brew_prefix = result.stdout.strip()
            version_file = Path(brew_prefix) / 'libexec' / 'VERSION'
            if version_file.exists():
                return version_file.read_text().strip()
    except Exception as e:
        logger.debug(f"Failed to get version from brew prefix: {e}")

    # 回退到本地 VERSION 文件
    version_file = SCRIPT_DIR.parent / 'VERSION'
    if version_file.exists():
        return version_file.read_text().strip()

    return None


def get_remote_version() -> Optional[str]:
    """从 GitHub API 获取最新版本"""
    try:
        req = Request(GITHUB_API_URL)
        req.add_header('User-Agent', 'BiliObjCLint-Updater')

        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data and len(data) > 0:
                # 获取第一个 tag（最新的）
                tag_name = data[0].get('name', '')
                # 去掉 'v' 前缀
                if tag_name.startswith('v'):
                    return tag_name[1:]
                return tag_name
    except Exception as e:
        logger.debug(f"Failed to get remote version: {e}")

    return None


def version_gt(v1: str, v2: str) -> bool:
    """比较版本号，v1 > v2 返回 True"""
    def version_tuple(v):
        return tuple(map(int, v.split('.')))

    try:
        return version_tuple(v1) > version_tuple(v2)
    except (ValueError, AttributeError):
        return False


def check_version_update() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    检查版本更新

    Returns:
        (需要更新, 本地版本, 远端版本)
    """
    local_ver = get_local_version()
    remote_ver = get_remote_version()

    logger.info(f"Local version: {local_ver}")
    logger.info(f"Remote version: {remote_ver}")

    if not local_ver or not remote_ver:
        return (False, local_ver, remote_ver)

    needs_update = version_gt(remote_ver, local_ver)
    return (needs_update, local_ver, remote_ver)


def get_changelog_for_version(version: str) -> str:
    """获取指定版本的 CHANGELOG"""
    try:
        # 尝试从 brew prefix 读取
        result = subprocess.run(
            ['brew', '--prefix', 'biliobjclint'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            brew_prefix = result.stdout.strip()
            # CHANGELOG.md is at Cellar root, not in libexec (Homebrew auto-extracts it)
            changelog_file = Path(brew_prefix) / 'CHANGELOG.md'
            if changelog_file.exists():
                content = changelog_file.read_text()
                # 查找对应版本的 changelog
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
        message += f"\n\n更新内容:\n{changelog[:500]}"  # 限制长度

    try:
        # 使用 osascript 显示弹窗
        script = f'''
        display dialog "{message}" with title "{title}" buttons {{"OK"}} default button "OK"
        '''
        subprocess.run(['osascript', '-e', script], capture_output=True, timeout=30)
    except Exception as e:
        logger.debug(f"Failed to show dialog: {e}")


def show_lint_phase_update_notification(old_version: str, new_version: str):
    """显示 Lint Phase 版本更新系统通知"""
    title = "BiliObjCLint"
    message = f"已同步 Code Style Lint 版本号 {old_version} ~ {new_version}"

    try:
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(['osascript', '-e', script], capture_output=True, timeout=10)
    except Exception as e:
        logger.debug(f"Failed to show lint phase update notification: {e}")


def background_upgrade(
    local_ver: str,
    remote_ver: str,
    scripts_dir: Optional[Path] = None,
    project_path: Optional[str] = None,
    target_name: Optional[str] = None,
    project_name: Optional[str] = None
):
    """
    后台执行 brew upgrade

    使用独立子进程执行更新，确保主进程退出后更新仍能继续。
    调用同级目录的 background_upgrade.py 脚本执行实际升级操作。
    升级完成后会更新 Build Phase。
    """
    logger.info(f"Starting background upgrade: {local_ver} -> {remote_ver}")

    # 构建命令参数
    upgrade_script = SCRIPT_DIR / 'background_upgrade.py'
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

        # 获取 venv Python 路径（brew upgrade 后需要使用新版本的 venv）
        # 由于 brew upgrade 会更新 symlink，这里获取的是当前（旧版本）的 venv
        # 但旧版本的 venv 也有 pbxproj，所以可以用来启动脚本
        # 脚本执行时会动态导入新版本的 xcode_integrator
        brew_prefix = get_brew_prefix()
        if brew_prefix:
            venv_python = brew_prefix / 'libexec' / '.venv' / 'bin' / 'python3'
            if venv_python.exists():
                python_path = str(venv_python)
            else:
                python_path = 'python3'
                logger.info(f"Venv python not found at {venv_python}, using system python3")
        else:
            python_path = 'python3'
            logger.info("brew prefix not found, using system python3")

        # 使用 shell 命令启动后台进程，确保日志重定向正确工作
        # nohup + & 确保进程完全脱离父进程
        # 使用 shlex.quote 确保所有参数正确转义（处理空格等特殊字符）
        args_quoted = ' '.join(shlex.quote(arg) for arg in args)
        script_path = shlex.quote(str(upgrade_script))
        log_path = shlex.quote(str(log_file))
        python_quoted = shlex.quote(python_path)
        shell_cmd = f'nohup {python_quoted} {script_path} {args_quoted} >> {log_path} 2>&1 &'

        # 将 shell 命令也写入日志文件，便于调试
        with open(log_file, 'a') as f:
            f.write(f"shell_cmd: {shell_cmd}\n")
            f.write("---\n")

        logger.info(f"Shell command: {shell_cmd}")

        subprocess.Popen(
            shell_cmd,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info(f"Background upgrade process started, log: {log_file}")
    except Exception as e:
        logger.exception(f"Failed to start background upgrade: {e}")


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


def do_check_and_inject(
    project_path: str,
    target_name: Optional[str] = None,
    project_name: Optional[str] = None,
    scripts_dir: Optional[str] = None,
    dry_run: bool = False
) -> bool:
    """
    检查更新并注入 Code Style Check Build Phase

    由 bootstrap.sh 在每次编译时调用

    Args:
        project_path: Xcode 项目路径
        target_name: Target 名称
        project_name: 项目名称（用于 workspace）
        scripts_dir: 项目 scripts 目录路径
        dry_run: 是否仅模拟运行

    Returns:
        是否成功
    """
    logger.info("Starting check and inject process")
    logger.info(f"Project: {project_path}")
    logger.info(f"Target: {target_name}")
    logger.info(f"Scripts dir: {scripts_dir}")

    # 1. 检查版本更新
    needs_update, local_ver, remote_ver = check_version_update()

    if needs_update:
        logger.info(f"Update available: {local_ver} -> {remote_ver}")
        print(f"[BiliObjCLint] 发现新版本: {local_ver} -> {remote_ver}")

        # 2. 后台执行 brew upgrade，传递项目信息以便升级后更新 Build Phase
        scripts_path = Path(scripts_dir) if scripts_dir else None
        background_upgrade(
            local_ver, remote_ver, scripts_path,
            project_path=project_path,
            target_name=target_name,
            project_name=project_name
        )
        return True

    # 3. 复制脚本到目标工程（如果不存在）
    if scripts_dir:
        scripts_path = Path(scripts_dir)
        copy_scripts_to_project(scripts_path, force=False)

    # 4. 导入 xcode_integrator 并注入 Build Phase
    try:
        from xcode_integrator import XcodeIntegrator, PHASE_NAME, SCRIPT_VERSION

        # 获取 lint_path
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

        # 5. 检查并注入/更新 Code Style Check Build Phase
        current_version = None  # 用于记录旧版本，判断是否为版本更新
        if integrator.has_lint_phase(target):
            # 检查版本是否需要更新
            current_version = integrator.get_lint_phase_version(target)
            if current_version and current_version != SCRIPT_VERSION:
                logger.info(f"Lint phase version mismatch: {current_version} -> {SCRIPT_VERSION}")
                print(f"[BiliObjCLint] 更新 Lint Phase 版本: {current_version} -> {SCRIPT_VERSION}")
                # 使用 override 更新 Build Phase
            else:
                logger.info(f"Target '{target.name}' already has lint phase with correct version")
                print(f"[BiliObjCLint] Target '{target.name}' 已存在 Lint Phase (v{current_version})")
                return True

        # 计算 scripts_path 相对于 SRCROOT 的路径
        srcroot = integrator.get_project_srcroot()
        if srcroot and scripts_dir:
            relative_path = os.path.relpath(scripts_dir, srcroot)
            scripts_path_in_phase = "${SRCROOT}/" + relative_path
        else:
            scripts_path_in_phase = "${SRCROOT}/../scripts"

        # 注入 Build Phase
        success = integrator.add_lint_phase(
            target,
            dry_run=dry_run,
            override=True,
            scripts_path=scripts_path_in_phase
        )

        if success and not dry_run:
            integrator.save()
            print(f"[BiliObjCLint] 已为 Target '{target.name}' 注入 Code Style Lint Phase")

            # 如果是版本更新（而非首次注入），且 brew 不需要更新，显示系统通知
            # brew 需要更新时，弹窗由 background_upgrade.py 处理
            if current_version and current_version != SCRIPT_VERSION and not needs_update:
                show_lint_phase_update_notification(current_version, SCRIPT_VERSION)

        return success

    except ImportError as e:
        logger.exception(f"Failed to import xcode_integrator: {e}")
        return False
    except Exception as e:
        logger.exception(f"Failed to inject build phase: {e}")
        return False


def parse_args():
    parser = argparse.ArgumentParser(
        description='BiliObjCLint 版本更新检查工具'
    )

    parser.add_argument(
        'project_path',
        nargs='?',
        help='Xcode 项目路径 (.xcodeproj 或 .xcworkspace)'
    )

    parser.add_argument(
        '--project', '-p',
        help='项目名称（用于 workspace 中指定项目）',
        default=None
    )

    parser.add_argument(
        '--target', '-t',
        help='Target 名称',
        default=None
    )

    parser.add_argument(
        '--scripts-dir',
        help='项目 scripts 目录路径',
        default=None
    )

    parser.add_argument(
        '--check-only',
        action='store_true',
        help='仅检查版本，不执行注入'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅显示将要进行的修改'
    )

    return parser.parse_args()


def main():
    args = parse_args()

    logger.log_separator("Check Update Session Start")
    logger.info(f"Arguments: {vars(args)}")

    if args.check_only:
        # 仅检查版本
        needs_update, local_ver, remote_ver = check_version_update()
        if local_ver is None:
            print("BiliObjCLint 未安装")
            sys.exit(1)
        elif needs_update:
            print(f"有新版本可用: {local_ver} -> {remote_ver}")
            sys.exit(2)
        else:
            print(f"已是最新版本: {local_ver}")
            sys.exit(0)

    if not args.project_path:
        print("Error: 请指定项目路径", file=sys.stderr)
        sys.exit(1)

    success = do_check_and_inject(
        project_path=args.project_path,
        target_name=args.target,
        project_name=args.project,
        scripts_dir=args.scripts_dir,
        dry_run=args.dry_run
    )

    logger.info(f"Check and inject completed: success={success}")
    logger.log_separator("Check Update Session End")

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
