#!/usr/bin/env python3
"""
BiliObjCLint - Bilibili Objective-C 代码规范检查工具

支持增量检查，使用 Python 规则引擎

Usage:
    python3 cli.py [options]

Options:
    --config PATH          配置文件路径 (默认: .biliobjclint.yaml)
    --project-root PATH    项目根目录 (默认: 当前目录)
    --incremental          增量检查模式 (只检查 git 变更)
    --base-branch BRANCH   增量对比基准分支 (默认: origin/master)
    --files FILE [FILE...] 指定要检查的文件
    --xcode-output         输出 Xcode 兼容格式
    --json-output          输出 JSON 格式
    --verbose              详细输出
    --help                 显示帮助
"""
import argparse
import os
import sys
from pathlib import Path

# 添加 scripts 目录到路径
SCRIPT_DIR = Path(__file__).parent
SCRIPTS_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.lint.logger import get_logger

from wrapper.lint.linter import BiliObjCLint


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="BiliObjCLint - Objective-C 代码规范检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--config", "-c",
        help="配置文件路径",
        default=None
    )

    parser.add_argument(
        "--project-root", "-p",
        help="项目根目录",
        default=os.getcwd()
    )

    parser.add_argument(
        "--incremental", "-i",
        action="store_true",
        help="增量检查模式（只检查 git 变更）"
    )

    parser.add_argument(
        "--base-branch", "-b",
        help="增量对比基准分支",
        default=None
    )

    parser.add_argument(
        "--files", "-f",
        nargs="+",
        help="指定要检查的文件"
    )

    parser.add_argument(
        "--xcode-output", "-x",
        action="store_true",
        default=True,
        help="输出 Xcode 兼容格式（默认启用）"
    )

    parser.add_argument(
        "--json-output", "-j",
        action="store_true",
        help="输出 JSON 格式"
    )

    # 内部参数：同时输出 Xcode 格式到 stdout 和 JSON 到指定文件
    # 用于 code_style_check.sh 优化，避免执行两次 lint
    parser.add_argument(
        "--json-file",
        help=argparse.SUPPRESS,  # 隐藏此参数，不在帮助中显示
        default=None
    )

    parser.add_argument(
        "--no-python-rules",
        action="store_true",
        help="禁用 Python 规则"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出"
    )

    return parser.parse_args()


def main():
    """主入口"""
    args = parse_args()
    logger = get_logger("biliobjclint")

    try:
        linter = BiliObjCLint(args)
        exit_code = linter.run()
        logger.debug(f"Exit code: {exit_code}")
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
