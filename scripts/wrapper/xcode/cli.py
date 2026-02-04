#!/usr/bin/env python3
"""
Xcode 项目集成工具命令行入口

自动为 Xcode 项目的指定 Target 添加 BiliObjCLint Build Phase

Usage:
    python3 cli.py <project_path> [options]

Options:
    --project, -p NAME      项目名称（用于 workspace 中指定项目）
    --target, -t NAME       Target 名称（默认：项目主 Target）
    --remove                移除已添加的 Lint Phase
    --list-projects         列出 workspace 中所有项目
    --list-targets          列出所有可用的 Targets
    --check-update          检查已注入脚本是否需要更新
    --bootstrap             复制 bootstrap.sh 并注入 Package Manager Build Phase
    --dry-run               仅显示将要进行的修改，不实际执行
    --help, -h              显示帮助
"""
import argparse
import sys
from pathlib import Path

# 添加 scripts 目录到路径
SCRIPT_DIR = Path(__file__).parent
SCRIPTS_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.lint.logger import get_logger

from wrapper.xcode.integrator import XcodeIntegrator


def parse_args():
    parser = argparse.ArgumentParser(
        description='BiliObjCLint Xcode 项目集成工具',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'project_path',
        help='Xcode 项目路径 (.xcodeproj 或 .xcworkspace)'
    )

    parser.add_argument(
        '--project', '-p',
        help='项目名称（用于 workspace 中指定项目）',
        default=None
    )

    parser.add_argument(
        '--target', '-t',
        help='Target 名称（默认：主 Target）',
        default=None
    )

    parser.add_argument(
        '--remove',
        action='store_true',
        help='移除 Lint Phase'
    )

    parser.add_argument(
        '--list-projects',
        action='store_true',
        help='列出 workspace 中所有项目'
    )

    parser.add_argument(
        '--list-targets',
        action='store_true',
        help='列出所有 Targets'
    )

    parser.add_argument(
        '--check-update',
        action='store_true',
        help='检查已注入脚本是否需要更新'
    )

    parser.add_argument(
        '--bootstrap',
        action='store_true',
        help='复制 bootstrap.sh 并注入 Package Manager Build Phase'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅显示将要进行的修改'
    )

    parser.add_argument(
        '--lint-path',
        help='BiliObjCLint 路径（默认：脚本所在目录的父目录）',
        default=None
    )

    parser.add_argument(
        '--override',
        action='store_true',
        help='强制覆盖已存在的 Lint Phase'
    )

    parser.add_argument(
        '--manual',
        action='store_true',
        help='显示手动配置说明（使用自动计算的路径）'
    )

    parser.add_argument(
        '--debug',
        help='启用调试模式，使用指定的本地开发目录（与 --bootstrap 配合使用）',
        default=None
    )

    return parser.parse_args()


def main():
    args = parse_args()
    logger = get_logger("xcode")

    logger.log_separator("Xcode Integration Session Start")
    logger.info(f"Project path: {args.project_path}")
    logger.debug(f"Arguments: {vars(args)}")

    # 确定 lint 路径
    lint_path = args.lint_path
    if not lint_path:
        # 从 wrapper/xcode/cli.py 到 scripts/../ (即 BiliObjCLint 根目录)
        lint_path = str(SCRIPTS_ROOT.parent)
    logger.debug(f"Lint path: {lint_path}")

    # 检查 debug 路径
    debug_path = args.debug
    if debug_path:
        logger.info(f"[DEBUG MODE] Using local dev path: {debug_path}")
        # 验证 debug 路径存在
        if not Path(debug_path).is_dir():
            print(f"Error: 调试路径不存在: {debug_path}", file=sys.stderr)
            sys.exit(1)

    # 创建集成器（传入 project 参数用于 workspace）
    integrator = XcodeIntegrator(args.project_path, lint_path, args.project, debug_path)

    # 如果是 workspace，先处理 --list-projects
    if args.list_projects:
        if Path(args.project_path).suffix != '.xcworkspace':
            print("Error: --list-projects 仅适用于 .xcworkspace", file=sys.stderr)
            sys.exit(1)
        projects = integrator.list_projects()
        logger.info(f"Listing {len(projects)} projects in workspace")
        print(f"\nWorkspace: {args.project_path}")
        print("可用的项目:")
        for name in projects:
            print(f"  - {name}")
        logger.log_separator("Xcode Integration Session End")
        sys.exit(0)

    # 加载项目
    if not integrator.load_project():
        logger.error("Failed to load project, exiting")
        sys.exit(1)

    print(f"项目: {integrator.xcodeproj_path}")

    # 显示手动配置说明
    if args.manual:
        integrator.show_manual()
        logger.log_separator("Xcode Integration Session End")
        sys.exit(0)

    # 列出 targets
    if args.list_targets:
        targets = integrator.list_targets()
        logger.info(f"Listing {len(targets)} targets")
        print("\n可用的 Targets:")
        for name in targets:
            print(f"  - {name}")
        logger.log_separator("Xcode Integration Session End")
        sys.exit(0)

    # 获取目标 target
    target = integrator.get_target(args.target)
    if not target:
        if args.target:
            logger.error(f"Target '{args.target}' not found")
            print(f"Error: Target '{args.target}' 不存在", file=sys.stderr)
            print("使用 --list-targets 查看可用的 Targets")
        else:
            logger.error("No available target found")
            print("Error: 未找到可用的 Target", file=sys.stderr)
        logger.log_separator("Xcode Integration Session End")
        sys.exit(1)

    logger.info(f"Selected target: {target.name}")
    print(f"Target: {target.name}")
    print()

    # Bootstrap 模式
    if args.bootstrap:
        logger.info("Executing bootstrap mode")
        success = integrator.do_bootstrap(args.target, args.dry_run)
        logger.info(f"Bootstrap completed: success={success}")
        logger.log_separator("Xcode Integration Session End")
        sys.exit(0 if success else 1)

    # 检查更新
    if args.check_update:
        needs_update, current_ver, latest_ver = integrator.check_update_needed(target)
        if current_ver is None:
            print(f"Lint Phase 未安装")
            sys.exit(1)
        elif needs_update:
            print(f"需要更新: {current_ver} -> {latest_ver}")
            sys.exit(2)  # 返回 2 表示需要更新
        else:
            print(f"已是最新版本: {current_ver}")
            sys.exit(0)

    # 执行操作
    if args.remove:
        logger.info("Executing remove operation")
        success = integrator.remove_lint_phase(target, args.dry_run)
    else:
        logger.info("Executing add operation")
        success = integrator.add_lint_phase(target, args.dry_run, args.override)
        if success:
            integrator.copy_config(args.dry_run)

    if success:
        integrator.save(args.dry_run)

    logger.info(f"Integration completed: success={success}")
    logger.log_separator("Xcode Integration Session End")

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
