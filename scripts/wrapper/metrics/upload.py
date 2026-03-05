#!/usr/bin/env python3
"""
BiliObjCLint - Metrics Background Upload

独立后台进程，负责将 spool 中积压的 metrics payload 上报到服务端。
由 code_style_check.sh 在 lint 完成后以后台进程启动，不阻塞 Xcode 编译。

Usage:
    python3 upload.py --config <config_path>
"""
import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SCRIPTS_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.lint.config import ConfigLoader
from core.lint.logger import get_logger
from core.lint import metrics as metrics_mod


def main():
    parser = argparse.ArgumentParser(description="BiliObjCLint Metrics Background Upload")
    parser.add_argument("--config", "-c", required=True, help="配置文件路径")
    args = parser.parse_args()

    logger = get_logger("biliobjclint")

    loader = ConfigLoader(args.config)
    config = loader.load()

    if not config.metrics.enabled:
        logger.debug("Metrics disabled, nothing to upload")
        return

    if not config.metrics.endpoint:
        logger.debug("Metrics endpoint empty, nothing to upload")
        return

    metrics_mod.flush_and_upload(config.metrics, logger)


if __name__ == "__main__":
    main()
