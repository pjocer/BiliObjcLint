#!/usr/bin/env python3
"""
BiliObjCLint Build Phase 更新脚本

独立脚本，由 upgrader.py 通过子进程调用。
在新版本的 Python 环境中执行，避免旧版本模块缓存问题。

Usage:
    python3 phase_updater.py --project-path /path/to/project.xcodeproj [options]
"""
import argparse
import sys
from pathlib import Path
from typing import Optional


def update_build_phase(
    project_path: str,
    target_name: Optional[str] = None,
    project_name: Optional[str] = None,
    scripts_dir: Optional[str] = None
) -> bool:
    """
    更新 Build Phase 到最新版本

    Args:
        project_path: Xcode 项目路径
        target_name: Target 名称
        project_name: 项目名称（用于 workspace）
        scripts_dir: scripts 目录路径

    Returns:
        是否成功
    """
    # 添加 scripts 目录到路径
    SCRIPT_DIR = Path(__file__).parent
    SCRIPTS_ROOT = SCRIPT_DIR.parent.parent
    sys.path.insert(0, str(SCRIPTS_ROOT))

    from wrapper.xcode import XcodeIntegrator, SCRIPT_VERSION
    from core.lint import project_config

    try:
        # 获取 brew prefix 作为 lint_path
        import subprocess
        result = subprocess.run(
            ['brew', '--prefix', 'biliobjclint'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            brew_prefix = Path(result.stdout.strip())
            lint_path = str(brew_prefix / 'libexec')
        else:
            lint_path = str(SCRIPTS_ROOT.parent)

        print(f"lint_path: {lint_path}")

        integrator = XcodeIntegrator(project_path, lint_path, project_name)

        if not integrator.load_project():
            print("ERROR: Failed to load project")
            return False

        target = integrator.get_target(target_name)
        if not target:
            print(f"ERROR: Target not found: {target_name}")
            return False

        current_version = None
        if integrator.has_lint_phase(target):
            current_version = integrator.get_lint_phase_version(target)
            print(f"Current Build Phase version: {current_version}")
            if current_version == SCRIPT_VERSION:
                print(f"Build Phase already at version {SCRIPT_VERSION}")
                return True

        # 从持久化存储获取项目配置
        config = project_config.get(str(integrator.xcodeproj_path), target.name)
        if config:
            scripts_path = project_config.get_scripts_srcroot_path(config)
            print(f"Scripts path: {config.scripts_dir_relative}")
        else:
            print("ERROR: No config found")
            return False

        # 更新 Build Phase
        success = integrator.add_lint_phase(
            target,
            dry_run=False,
            override=True,
            scripts_path=scripts_path
        )

        if success:
            integrator.save()
            print(f"Build Phase updated: {current_version} -> {SCRIPT_VERSION}")
        else:
            print("ERROR: Failed to update Build Phase")

        return success

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def parse_args():
    parser = argparse.ArgumentParser(
        description='BiliObjCLint Build Phase 更新脚本'
    )

    parser.add_argument(
        '--project-path',
        required=True,
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

    parser.add_argument(
        '--scripts-dir',
        default=None,
        help='scripts 目录路径'
    )

    return parser.parse_args()


def main():
    args = parse_args()

    print(f"=== Phase Updater Started ===")
    print(f"Project path: {args.project_path}")
    print(f"Target name: {args.target_name}")
    print(f"Project name: {args.project_name}")

    success = update_build_phase(
        args.project_path,
        args.target_name,
        args.project_name,
        args.scripts_dir
    )

    print(f"=== Phase Updater Finished: {'SUCCESS' if success else 'FAILED'} ===")
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
