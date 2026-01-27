#!/usr/bin/env python3
"""
Xcode 项目集成工具

自动为 Xcode 项目的指定 Target 添加 BiliObjCLint Build Phase

Usage:
    python3 xcode_integrator.py <project_path> [options]

Options:
    --project, -p NAME      项目名称（用于 workspace 中指定项目）
    --target, -t NAME       Target 名称（默认：项目主 Target）
    --remove                移除已添加的 Lint Phase
    --list-projects         列出 workspace 中所有项目
    --list-targets          列出所有可用的 Targets
    --check-update          检查已注入脚本是否需要更新
    --dry-run               仅显示将要进行的修改，不实际执行
    --help, -h              显示帮助
"""
import argparse
import os
import sys
import shutil
from pathlib import Path
from typing import Optional, List
import xml.etree.ElementTree as ET

from pbxproj import XcodeProject
from pbxproj.pbxextensions import ProjectFiles

# 添加 scripts 目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from core.logger import get_logger


def get_version() -> str:
    """从 VERSION 文件读取版本号"""
    version_file = Path(__file__).parent.parent / 'VERSION'
    if version_file.exists():
        return version_file.read_text().strip()
    return "1.0.0"


# 脚本版本号（动态读取）
SCRIPT_VERSION = get_version()

# Build Phase 脚本模板
LINT_SCRIPT_TEMPLATE = '''#!/bin/bash

# BiliObjCLint - Objective-C 代码规范检查
# Version: {version}
# 自动生成，请勿手动修改

LINT_PATH="{lint_path}"
CONFIG_PATH="${{SRCROOT}}/.biliobjclint.yaml"
PYTHON_BIN="${{LINT_PATH}}/.venv/bin/python3"

# 加载日志库
if [ -f "${{LINT_PATH}}/scripts/lib/logging.sh" ]; then
    source "${{LINT_PATH}}/scripts/lib/logging.sh"
    init_logging "xcode_build_phase"
    log_script_start "Build Phase Lint Check"
    log_info "Project: ${{SRCROOT}}"
    log_info "Configuration: ${{CONFIGURATION}}"
else
    # 如果日志库不存在，定义空函数
    log_info() {{ :; }}
    log_debug() {{ :; }}
    log_warn() {{ :; }}
    log_error() {{ :; }}
fi

# Release 模式跳过
if [ "${{CONFIGURATION}}" == "Release" ]; then
    log_info "Release mode, skipping lint check"
    echo "Release 模式，跳过 Lint 检查"
    exit 0
fi

# 检查 venv
if [ ! -f "$PYTHON_BIN" ]; then
    log_warn "BiliObjCLint venv not initialized"
    echo "warning: BiliObjCLint venv 未初始化，请运行 ${{LINT_PATH}}/scripts/setup_env.sh"
    exit 0
fi

log_info "Python binary: $PYTHON_BIN"

# 创建临时文件存储 JSON 输出
VIOLATIONS_FILE=$(mktemp)
log_debug "Violations temp file: $VIOLATIONS_FILE"

# 执行 Lint 检查，输出 JSON 格式到临时文件
log_info "Running lint check (JSON output)..."
"$PYTHON_BIN" "${{LINT_PATH}}/scripts/biliobjclint.py" \\
    --config "$CONFIG_PATH" \\
    --project-root "${{SRCROOT}}" \\
    --incremental \\
    --json-output > "$VIOLATIONS_FILE" 2>/dev/null

# 执行 Lint 检查，输出 Xcode 格式（用于在 Xcode 中显示警告/错误）
log_info "Running lint check (Xcode output)..."
"$PYTHON_BIN" "${{LINT_PATH}}/scripts/biliobjclint.py" \\
    --config "$CONFIG_PATH" \\
    --project-root "${{SRCROOT}}" \\
    --incremental \\
    --xcode-output

LINT_EXIT=$?
log_info "Lint exit code: $LINT_EXIT"

# 如果有违规，调用 Claude 修复模块
if [ -s "$VIOLATIONS_FILE" ] && [ $LINT_EXIT -ne 0 ]; then
    # 保存违规信息到固定位置
    VIOLATIONS_COPY="/tmp/biliobjclint_violations_$$.json"
    cp "$VIOLATIONS_FILE" "$VIOLATIONS_COPY"
    log_debug "Violations copied to: $VIOLATIONS_COPY"

    # 获取违规统计
    TOTAL=$(cat "$VIOLATIONS_FILE" | /usr/bin/python3 -c "import sys,json; print(json.load(sys.stdin).get('summary',{{}}).get('total',0))" 2>/dev/null || echo "0")
    ERRORS=$(cat "$VIOLATIONS_FILE" | /usr/bin/python3 -c "import sys,json; print(json.load(sys.stdin).get('summary',{{}}).get('errors',0))" 2>/dev/null || echo "0")
    log_info "Violations found: $TOTAL total, $ERRORS errors"

    # 在进入后台子进程前，先保存所有需要的变量值
    # 因为 Xcode 环境变量在后台子进程中可能不可用
    _PYTHON_BIN="$PYTHON_BIN"
    _LINT_PATH="{lint_path}"
    _CONFIG_PATH="$CONFIG_PATH"
    _PROJECT_ROOT="${{SRCROOT}}"
    _VIOLATIONS_COPY="$VIOLATIONS_COPY"

    log_info "Launching Claude fix dialog in background..."

    # 使用 AppleScript 显示对话框（通过 osascript 在后台运行）
    # 这会在用户的桌面环境中显示对话框，而不是在 Xcode 的沙盒中
    (
        RESPONSE=$(osascript -e "
        display alert \\"BiliObjCLint 发现 $TOTAL 个代码问题\\" message \\"其中 $ERRORS 个错误。\\n\\n是否让 Claude 尝试自动修复？\\" as warning buttons {{\\"取消\\", \\"自动修复\\"}} default button \\"自动修复\\" cancel button \\"取消\\"
        " 2>&1)

        if echo "$RESPONSE" | grep -q "自动修复"; then
            # 用户点击了自动修复，执行修复
            osascript -e "display notification \\"Claude 正在修复代码...\\" with title \\"BiliObjCLint\\""

            "$_PYTHON_BIN" "$_LINT_PATH/scripts/claude_fixer.py" \\
                --violations "$_VIOLATIONS_COPY" \\
                --config "$_CONFIG_PATH" \\
                --project-root "$_PROJECT_ROOT" \\
                --skip-dialog

            FIX_EXIT=$?

            if [ $FIX_EXIT -eq 0 ]; then
                osascript -e "display notification \\"修复完成，请重新编译验证\\" with title \\"BiliObjCLint\\" sound name \\"Glass\\""
            else
                osascript -e "display alert \\"BiliObjCLint 修复失败\\" message \\"详情请查看日志：$_LINT_PATH/logs/\\" as critical buttons {{\\"确定\\"}} default button \\"确定\\""
            fi
        fi

        rm -f "$_VIOLATIONS_COPY"
    ) &
fi

# 清理临时文件
rm -f "$VIOLATIONS_FILE"
log_debug "Temp file cleaned up"

log_info "Build phase completed with exit code: $LINT_EXIT"
exit $LINT_EXIT
'''

PHASE_NAME = "[BiliObjCLint] Code Style Check"


class XcodeIntegrator:
    """Xcode 项目集成器"""

    def __init__(self, project_path: str, lint_path: str, project_name: Optional[str] = None):
        self.project_path = Path(project_path).resolve()
        self.lint_path = Path(lint_path).resolve()
        self.project_name = project_name  # 用于 workspace 中指定项目
        self.xcodeproj_path: Optional[Path] = None
        self.project: Optional[XcodeProject] = None
        self.logger = get_logger("xcode")

        self.logger.info(f"XcodeIntegrator initialized")
        self.logger.debug(f"Project path: {self.project_path}")
        self.logger.debug(f"Lint path: {self.lint_path}")
        self.logger.debug(f"Project name filter: {self.project_name}")

    def load_project(self) -> bool:
        """加载 Xcode 项目"""
        self.logger.info(f"Loading project: {self.project_path}")

        # 处理 .xcworkspace
        if self.project_path.suffix == '.xcworkspace':
            self.logger.debug("Detected .xcworkspace, searching for project...")
            self.xcodeproj_path = self._find_project_in_workspace(self.project_name)
            if not self.xcodeproj_path:
                self.logger.error("Cannot find project in workspace")
                if self.project_name:
                    print(f"Error: 在 workspace 中找不到项目 '{self.project_name}'", file=sys.stderr)
                    print("使用 --list-projects 查看可用的项目")
                else:
                    print(f"Error: 无法在 workspace 中找到项目", file=sys.stderr)
                return False
        elif self.project_path.suffix == '.xcodeproj':
            self.xcodeproj_path = self.project_path
        else:
            # 尝试在目录中查找
            self.logger.debug("Searching for project in directory...")
            self.xcodeproj_path = self._find_project_in_directory()
            if not self.xcodeproj_path:
                self.logger.error(f"Cannot find Xcode project: {self.project_path}")
                print(f"Error: 无法找到 Xcode 项目: {self.project_path}", file=sys.stderr)
                return False

        self.logger.debug(f"Found xcodeproj: {self.xcodeproj_path}")

        # 加载项目
        pbxproj_path = self.xcodeproj_path / 'project.pbxproj'
        if not pbxproj_path.exists():
            self.logger.error(f"Project file not found: {pbxproj_path}")
            print(f"Error: 项目文件不存在: {pbxproj_path}", file=sys.stderr)
            return False

        try:
            self.project = XcodeProject.load(str(pbxproj_path))
            self.logger.info(f"Project loaded successfully: {self.xcodeproj_path}")
            return True
        except Exception as e:
            self.logger.exception(f"Failed to load project: {e}")
            print(f"Error: 加载项目失败: {e}", file=sys.stderr)
            return False

    def _get_projects_in_workspace(self) -> List[Path]:
        """获取 workspace 中所有项目"""
        contents_path = self.project_path / 'contents.xcworkspacedata'
        if not contents_path.exists():
            return []

        projects = []
        try:
            tree = ET.parse(contents_path)
            root = tree.getroot()

            for file_ref in root.findall('.//FileRef'):
                location = file_ref.get('location', '')
                rel_path = None
                if location.startswith('group:'):
                    rel_path = location[6:]
                elif location.startswith('container:'):
                    rel_path = location[10:]

                if rel_path:
                    full_path = self.project_path.parent / rel_path
                    if full_path.suffix == '.xcodeproj' and full_path.exists():
                        projects.append(full_path)

        except Exception as e:
            print(f"Warning: 解析 workspace 失败: {e}", file=sys.stderr)

        return projects

    def list_projects(self) -> List[str]:
        """列出 workspace 中所有项目名称"""
        projects = self._get_projects_in_workspace()
        return [p.stem for p in projects]

    def _find_project_in_workspace(self, project_name: Optional[str] = None) -> Optional[Path]:
        """从 workspace 中找到指定项目（或第一个项目）"""
        projects = self._get_projects_in_workspace()

        if not projects:
            return None

        if project_name:
            # 按名称查找
            for proj in projects:
                if proj.stem == project_name:
                    return proj
            return None
        else:
            # 返回第一个非 Pods 项目
            for proj in projects:
                if proj.stem != 'Pods':
                    return proj
            return projects[0] if projects else None

    def _find_project_in_directory(self) -> Optional[Path]:
        """在目录中查找 .xcodeproj"""
        if self.project_path.is_dir():
            for item in self.project_path.iterdir():
                if item.suffix == '.xcodeproj':
                    return item
        return None

    def list_targets(self) -> List[str]:
        """列出所有 Targets"""
        if not self.project:
            return []

        targets = []
        for target in self.project.objects.get_targets():
            targets.append(target.name)
        return targets

    def get_target(self, target_name: Optional[str] = None):
        """获取指定 Target，如果未指定则返回第一个 Native Target"""
        if not self.project:
            return None

        targets = self.project.objects.get_targets()

        if target_name:
            for target in targets:
                if target.name == target_name:
                    return target
            return None
        else:
            # 返回第一个 native target（通常是主 App）
            for target in targets:
                if target.isa == 'PBXNativeTarget':
                    # 优先选择 application 类型
                    if hasattr(target, 'productType') and 'application' in str(target.productType):
                        return target

            # 如果没找到 application，返回第一个 native target
            for target in targets:
                if target.isa == 'PBXNativeTarget':
                    return target

            return targets[0] if targets else None

    def has_lint_phase(self, target) -> bool:
        """检查是否已存在 Lint Phase"""
        build_phases = target.buildPhases
        for phase_id in build_phases:
            phase = self.project.objects[phase_id]
            if phase.isa == 'PBXShellScriptBuildPhase':
                if hasattr(phase, 'name') and phase.name == PHASE_NAME:
                    return True
                # 也检查脚本内容
                if hasattr(phase, 'shellScript') and 'BiliObjCLint' in str(phase.shellScript):
                    return True
        return False

    def get_lint_phase_version(self, target) -> Optional[str]:
        """获取已注入 Lint Phase 的版本号"""
        import re
        build_phases = target.buildPhases
        for phase_id in build_phases:
            phase = self.project.objects[phase_id]
            if phase.isa == 'PBXShellScriptBuildPhase':
                if hasattr(phase, 'shellScript') and 'BiliObjCLint' in str(phase.shellScript):
                    script = str(phase.shellScript)
                    # 匹配 "# Version: x.x.x"
                    match = re.search(r'# Version: (\d+\.\d+\.\d+)', script)
                    if match:
                        return match.group(1)
                    # 旧版本没有版本号
                    return "0.0.0"
        return None

    def check_update_needed(self, target) -> tuple:
        """
        检查是否需要更新
        返回: (需要更新, 当前版本, 最新版本)
        """
        current_version = self.get_lint_phase_version(target)
        if current_version is None:
            return (False, None, SCRIPT_VERSION)  # 没有安装

        # 简单版本比较
        def version_tuple(v):
            return tuple(map(int, v.split('.')))

        needs_update = version_tuple(current_version) < version_tuple(SCRIPT_VERSION)
        return (needs_update, current_version, SCRIPT_VERSION)

    def add_lint_phase(self, target, dry_run: bool = False, override: bool = False) -> bool:
        """添加 Lint Build Phase"""
        self.logger.info(f"Adding lint phase to target: {target.name}")

        if self.has_lint_phase(target):
            if override:
                self.logger.info(f"Target '{target.name}' already has lint phase, overriding...")
                print(f"Target '{target.name}' 已存在 Lint Phase，将覆盖更新")
                self.remove_lint_phase(target, dry_run)
            else:
                self.logger.info(f"Target '{target.name}' already has lint phase, skipping")
                print(f"Target '{target.name}' 已存在 Lint Phase，跳过（使用 --override 强制覆盖）")
                return True

        script_content = LINT_SCRIPT_TEMPLATE.format(
            version=SCRIPT_VERSION,
            lint_path=str(self.lint_path)
        )
        self.logger.debug(f"Generated script content ({len(script_content)} chars)")

        if dry_run:
            self.logger.info(f"[DRY RUN] Would add lint phase to target '{target.name}'")
            print(f"[DRY RUN] 将为 Target '{target.name}' 添加 Build Phase:")
            print(f"  名称: {PHASE_NAME}")
            print(f"  位置: Compile Sources 之前")
            return True

        try:
            # 使用 pbxproj 的 add_run_script 方法
            self.project.add_run_script(
                script=script_content,
                target_name=target.name,
                insert_before_compile=True  # 在 Compile Sources 之前插入
            )

            # 找到刚添加的 phase 并设置名称
            for phase_id in target.buildPhases:
                phase = self.project.objects[phase_id]
                if phase.isa == 'PBXShellScriptBuildPhase':
                    if hasattr(phase, 'shellScript') and 'BiliObjCLint' in str(phase.shellScript):
                        if not hasattr(phase, 'name') or not phase.name:
                            phase.name = PHASE_NAME
                        break

            self.logger.info(f"Successfully added lint phase to target '{target.name}'")
            print(f"✓ 已为 Target '{target.name}' 添加 Lint Phase")
            return True

        except Exception as e:
            self.logger.exception(f"Failed to add build phase: {e}")
            print(f"Error: 添加 Build Phase 失败: {e}", file=sys.stderr)
            return False

    def remove_lint_phase(self, target, dry_run: bool = False) -> bool:
        """移除 Lint Build Phase"""
        self.logger.info(f"Removing lint phase from target: {target.name}")

        build_phases = list(target.buildPhases)
        phases_to_remove = []

        for phase_id in build_phases:
            phase = self.project.objects[phase_id]
            if phase.isa == 'PBXShellScriptBuildPhase':
                should_remove = False
                if hasattr(phase, 'name') and phase.name == PHASE_NAME:
                    should_remove = True
                elif hasattr(phase, 'shellScript') and 'BiliObjCLint' in str(phase.shellScript):
                    should_remove = True

                if should_remove:
                    phases_to_remove.append(phase_id)

        if not phases_to_remove:
            self.logger.info(f"Target '{target.name}' does not have lint phase")
            print(f"Target '{target.name}' 不存在 Lint Phase")
            return True

        self.logger.debug(f"Found {len(phases_to_remove)} lint phases to remove")

        if dry_run:
            self.logger.info(f"[DRY RUN] Would remove {len(phases_to_remove)} lint phases")
            print(f"[DRY RUN] 将从 Target '{target.name}' 移除 {len(phases_to_remove)} 个 Lint Phase")
            return True

        for phase_id in phases_to_remove:
            build_phases.remove(phase_id)
            del self.project.objects[phase_id]

        target.buildPhases = build_phases
        self.logger.info(f"Successfully removed lint phase from target '{target.name}'")
        print(f"✓ 已从 Target '{target.name}' 移除 Lint Phase")
        return True

    def save(self, dry_run: bool = False) -> bool:
        """保存项目修改"""
        self.logger.info("Saving project changes...")

        if dry_run:
            self.logger.info("[DRY RUN] Not saving changes")
            print("[DRY RUN] 不保存修改")
            return True

        if not self.project:
            self.logger.error("No project loaded, cannot save")
            return False

        try:
            self.project.save()
            self.logger.info(f"Project saved successfully: {self.xcodeproj_path}")
            print(f"✓ 项目已保存: {self.xcodeproj_path}")
            return True

        except Exception as e:
            self.logger.exception(f"Failed to save project: {e}")
            print(f"Error: 保存项目失败: {e}", file=sys.stderr)
            return False

    def copy_config(self, dry_run: bool = False) -> bool:
        """复制配置文件到项目目录（传入路径的父目录）"""
        self.logger.info("Copying config file...")

        # 使用传入路径的父目录，而不是解析出的 xcodeproj 的父目录
        # 这样可以正确处理 .xcworkspace 和 .xcodeproj 的情况
        if self.project_path.suffix in ['.xcworkspace', '.xcodeproj']:
            config_dir = self.project_path.parent
        else:
            config_dir = self.project_path
        config_dest = config_dir / '.biliobjclint.yaml'
        config_src = self.lint_path / 'config' / 'default.yaml'

        self.logger.debug(f"Config source: {config_src}")
        self.logger.debug(f"Config destination: {config_dest}")

        if config_dest.exists():
            self.logger.info(f"Config file already exists: {config_dest}")
            print(f"配置文件已存在: {config_dest}")
            return True

        if dry_run:
            self.logger.info(f"[DRY RUN] Would copy config to: {config_dest}")
            print(f"[DRY RUN] 将复制配置文件到: {config_dest}")
            return True

        try:
            shutil.copy2(config_src, config_dest)
            self.logger.info(f"Config file copied to: {config_dest}")
            print(f"✓ 配置文件已复制: {config_dest}")
            return True
        except Exception as e:
            self.logger.exception(f"Failed to copy config: {e}")
            print(f"Error: 复制配置文件失败: {e}", file=sys.stderr)
            return False


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
        lint_path = str(Path(__file__).parent.parent)
    logger.debug(f"Lint path: {lint_path}")

    # 创建集成器（传入 project 参数用于 workspace）
    integrator = XcodeIntegrator(args.project_path, lint_path, args.project)

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
