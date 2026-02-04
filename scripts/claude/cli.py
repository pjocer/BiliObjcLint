"""
Claude Fixer - 命令行入口模块

处理命令行参数并启动修复流程
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

# 添加 scripts 目录到路径以支持绝对导入
_SCRIPT_DIR = Path(__file__).parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from core.lint.logger import get_logger
from claude.fixer import ClaudeFixer

logger = get_logger("claude_fix")


def load_config(config_path: str) -> dict:
    """加载配置文件"""
    if not config_path or not os.path.exists(config_path):
        return {}

    try:
        import yaml
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # 如果没有 PyYAML，尝试简单解析
        return {}
    except Exception:
        return {}


def load_violations(violations_path: str) -> Tuple[List[Dict], Dict[str, Any]]:
    """加载违规信息与元数据"""
    if not violations_path or not os.path.exists(violations_path):
        return [], {}

    try:
        with open(violations_path, 'r') as f:
            content = f.read().strip()
            if not content:
                return [], {}
            data = json.loads(content)
            return data.get('violations', []), data
    except json.JSONDecodeError:
        return [], {}
    except Exception:
        return [], {}


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='Claude 自动修复工具'
    )

    parser.add_argument(
        '--violations',
        help='违规信息 JSON 文件路径',
        required=False
    )

    parser.add_argument(
        '--config',
        help='配置文件路径',
        required=False
    )

    parser.add_argument(
        '--project-root',
        help='项目根目录',
        default=os.getcwd()
    )

    parser.add_argument(
        '--check-only',
        action='store_true',
        help='仅检测 Claude CLI 是否可用'
    )

    parser.add_argument(
        '--skip-dialog',
        action='store_true',
        help='跳过询问对话框，直接执行修复（用于 Build Phase 脚本已处理对话框的情况）'
    )

    return parser.parse_args()


def main():
    """主入口"""
    # 调试：写入临时文件追踪执行
    debug_file = "/tmp/biliobjclint_debug.log"
    with open(debug_file, "a") as f:
        f.write(f"\n=== {datetime.datetime.now()} ===\n")
        f.write(f"claude_fixer.py started\n")
        f.write(f"sys.argv: {sys.argv}\n")

    args = parse_args()

    # 调试：记录参数
    with open(debug_file, "a") as f:
        f.write(f"args: {vars(args)}\n")

    logger.info(f"Claude fixer started: project_root={args.project_root}")
    logger.debug(f"Arguments: {vars(args)}")

    # 加载配置
    config = load_config(args.config)
    logger.debug(f"Config loaded from: {args.config}")

    # 加载违规信息（含元数据）
    violations, meta = load_violations(args.violations)
    logger.info(f"Loaded {len(violations)} violations from: {args.violations}")

    run_id = meta.get("run_id") if isinstance(meta, dict) else None
    project = meta.get("project", {}) if isinstance(meta, dict) else {}

    # 创建修复器
    fixer = ClaudeFixer(config, args.project_root, run_id=run_id, project=project)

    # 仅检测模式
    if args.check_only:
        logger.info("Running in check-only mode")
        available, error_msg = fixer.check_claude_available()
        if available:
            print("Claude Code CLI 可用")
            logger.info("Check completed: Claude CLI is available")
            sys.exit(0)
        else:
            print(f"Claude Code CLI 不可用: {error_msg}", file=sys.stderr)
            logger.error(f"Check completed: Claude CLI not available - {error_msg}")
            sys.exit(1)

    if not violations:
        # 没有违规，直接退出
        logger.info("No violations to process, exiting")
        sys.exit(0)

    # 根据参数选择执行模式
    if args.skip_dialog:
        # 跳过对话框，直接执行静默修复
        logger.info("Running in skip-dialog mode (silent fix)")
        exit_code = fixer.run_silent_fix(violations)
    else:
        # 完整流程（包含询问对话框）
        logger.info("Running in full dialog mode")
        exit_code = fixer.run(violations)

    # 发送 autofix 统计（不影响结果）
    try:
        from core.lint import metrics as metrics_mod
        if run_id:
            payload = metrics_mod.build_autofix_payload(
                run_id=run_id,
                config=fixer.metrics_config,
                project_key=fixer.project_key,
                project_name=fixer.project_name,
                tool_version=fixer.tool_version,
                autofix=fixer.get_autofix_report(),
            )
            metrics_mod.send_payload(payload, fixer.metrics_config, logger)
    except Exception as e:
        logger.warning(f"Autofix metrics send failed: {e}")

    logger.info(f"Claude fixer completed with exit code: {exit_code}")
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
