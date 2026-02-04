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
    --bootstrap             复制 bootstrap.sh 并注入 Package Manager Build Phase
    --dry-run               仅显示将要进行的修改，不实际执行
    --help, -h              显示帮助
"""
import argparse
import os
import sys
import shutil
import stat
from pathlib import Path
from typing import Optional, List
import xml.etree.ElementTree as ET

from pbxproj import XcodeProject
from pbxproj.pbxextensions import ProjectFiles

# 添加 scripts 目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from core.lint.logger import get_logger


def get_version() -> str:
    """从 VERSION 文件读取版本号"""
    version_file = Path(__file__).parent.parent / 'VERSION'
    if version_file.exists():
        return version_file.read_text().strip()
    return "1.0.0"


# 脚本版本号（动态读取）
SCRIPT_VERSION = get_version()

# Build Phase 脚本模板（调用外部脚本）
# 用于 --bootstrap 模式，调用复制到项目中的 code_style_check.sh
LINT_SCRIPT_TEMPLATE = '''#!/bin/bash
# [BiliObjcLint] Code Style Check
# 代码规范审查
# Version: {version}

"{scripts_path}/code_style_check.sh"
'''

PHASE_NAME = "[BiliObjcLint] Code Style Lint"
BOOTSTRAP_PHASE_NAME = "[BiliObjcLint] Package Manager"

# Bootstrap Build Phase 脚本模板
# bootstrap.sh 直接从 Xcode 环境变量读取 PROJECT_FILE_PATH 和 TARGET_NAME
BOOTSTRAP_SCRIPT_TEMPLATE = '''#!/bin/bash
# [BiliObjcLint] Package Manager
# 自动安装和更新 BiliObjCLint

"{scripts_path}/bootstrap.sh"
'''

# 导入项目配置模块
from core.lint import project_config


class XcodeIntegrator:
    """Xcode 项目集成器"""

    def __init__(self, project_path: str, lint_path: str, project_name: Optional[str] = None,
                 debug_path: Optional[str] = None):
        self.project_path = Path(project_path).resolve()
        self.lint_path = Path(lint_path).resolve()
        self.project_name = project_name  # 用于 workspace 中指定项目
        self.debug_path = Path(debug_path).resolve() if debug_path else None  # 本地开发目录
        self.xcodeproj_path: Optional[Path] = None
        self.project: Optional[XcodeProject] = None
        self.logger = get_logger("xcode")

        self.logger.info(f"XcodeIntegrator initialized")
        self.logger.debug(f"Project path: {self.project_path}")
        self.logger.debug(f"Lint path: {self.lint_path}")
        self.logger.debug(f"Project name filter: {self.project_name}")
        if self.debug_path:
            self.logger.info(f"[DEBUG MODE] Using local dev path: {self.debug_path}")

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
                # 排除 Package Manager phase
                phase_name = getattr(phase, 'name', '')
                if phase_name == BOOTSTRAP_PHASE_NAME:
                    continue
                if phase_name == PHASE_NAME:
                    return True
                # 也检查脚本内容（排除 Package Manager）
                if hasattr(phase, 'shellScript'):
                    script = str(phase.shellScript)
                    if 'Code Style Check' in script or '# Version:' in script:
                        return True
        return False

    def get_lint_phase_version(self, target) -> Optional[str]:
        """获取已注入 Lint Phase 的版本号"""
        import re
        build_phases = target.buildPhases
        for phase_id in build_phases:
            phase = self.project.objects[phase_id]
            if phase.isa == 'PBXShellScriptBuildPhase':
                # 排除 Package Manager phase
                phase_name = getattr(phase, 'name', '')
                if phase_name == BOOTSTRAP_PHASE_NAME:
                    continue
                if hasattr(phase, 'shellScript'):
                    script = str(phase.shellScript)
                    # 只检查 Code Style Check phase
                    if 'Code Style Check' in script or '# Version:' in script:
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

    def add_lint_phase(self, target, dry_run: bool = False, override: bool = False,
                       scripts_path: Optional[str] = None) -> bool:
        """
        添加 Lint Build Phase

        注入位置规则：
        1. 如果存在 [BiliObjcLint] Package Manager，则插入到它后面
        2. 如果不存在 Package Manager，则插入到 Compile Sources 前面

        Args:
            target: Target 对象
            dry_run: 是否仅模拟运行
            override: 是否强制覆盖
            scripts_path: scripts 目录相对于 SRCROOT 的路径（用于 bootstrap 模式）
        """
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

        # 获取 scripts_path（如果未提供）
        if not scripts_path:
            # 从持久化存储读取配置
            config = project_config.get(str(self.xcodeproj_path), target.name)
            if config:
                scripts_path = project_config.get_scripts_srcroot_path(config)
                self.logger.debug(f"Loaded scripts path from config: {config.scripts_dir_relative}")
            else:
                # 没有保存的配置，需要先执行 --bootstrap
                key = project_config.make_key(str(self.xcodeproj_path), target.name)
                self.logger.error(f"No config found for key: {key}")
                print("Error: 未找到项目配置，请先执行 --bootstrap", file=sys.stderr)
                return False

        script_content = LINT_SCRIPT_TEMPLATE.format(
            version=SCRIPT_VERSION,
            scripts_path=scripts_path
        )
        self.logger.debug(f"Generated script content ({len(script_content)} chars)")
        self.logger.debug(f"Scripts path: {scripts_path}")

        # 确定插入位置
        bootstrap_index = self._get_bootstrap_phase_index(target)
        compile_index = self._get_compile_sources_index(target)

        if bootstrap_index >= 0:
            # Package Manager 存在，插入到它后面
            insert_index = bootstrap_index + 1
            position_desc = f"Package Manager 后面 (index {insert_index})"
        elif compile_index >= 0:
            # Package Manager 不存在，插入到 Compile Sources 前面
            insert_index = compile_index
            position_desc = f"Compile Sources 前面 (index {insert_index})"
        else:
            # 都不存在，插入到最前面
            insert_index = 0
            position_desc = "Build Phases 最前面 (index 0)"

        self.logger.debug(f"Determined insert position: {position_desc}")

        if dry_run:
            self.logger.info(f"[DRY RUN] Would add lint phase to target '{target.name}'")
            print(f"[DRY RUN] 将为 Target '{target.name}' 添加 Build Phase:")
            print(f"  名称: {PHASE_NAME}")
            print(f"  位置: {position_desc}")
            return True

        try:
            # 创建 Shell Script Build Phase
            phase_id = self._create_shell_script_phase(script_content, PHASE_NAME)

            # 插入到计算出的位置
            self._insert_phase_at_index(target, phase_id, insert_index)

            self.logger.info(f"Successfully added lint phase to target '{target.name}' at {position_desc}")
            print(f"✓ 已为 Target '{target.name}' 添加 Lint Phase（位于 {position_desc}）")
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
                # 排除 Package Manager phase
                phase_name = getattr(phase, 'name', '')
                if phase_name == BOOTSTRAP_PHASE_NAME:
                    continue

                should_remove = False
                if phase_name == PHASE_NAME:
                    should_remove = True
                elif hasattr(phase, 'shellScript'):
                    script = str(phase.shellScript)
                    # 只移除 Code Style Check phase，不移除 Package Manager
                    if 'Code Style Check' in script or '# Version:' in script:
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

        # 获取 pbxproj 文件路径
        pbxproj_path = self.xcodeproj_path / "project.pbxproj"
        backup_path = self.xcodeproj_path / "project.pbxproj.backup"

        try:
            # 创建备份
            if pbxproj_path.exists():
                import shutil
                shutil.copy2(pbxproj_path, backup_path)
                original_size = pbxproj_path.stat().st_size
                self.logger.info(f"Created backup: {backup_path} (size: {original_size})")

            # 保存项目
            self.project.save()

            # 验证保存结果
            if pbxproj_path.exists():
                new_size = pbxproj_path.stat().st_size
                self.logger.info(f"Saved file size: {new_size}")

                # 检查文件是否被清空
                if new_size == 0:
                    self.logger.error("CRITICAL: Project file became empty after save!")
                    # 从备份恢复
                    if backup_path.exists():
                        shutil.copy2(backup_path, pbxproj_path)
                        self.logger.info("Restored from backup")
                        print(f"Error: 项目文件保存异常，已从备份恢复", file=sys.stderr)
                    return False

                # 验证文件格式
                import subprocess
                result = subprocess.run(
                    ['plutil', '-lint', str(pbxproj_path)],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    self.logger.error(f"Project file validation failed: {result.stderr}")
                    # 从备份恢复
                    if backup_path.exists():
                        shutil.copy2(backup_path, pbxproj_path)
                        self.logger.info("Restored from backup due to validation failure")
                        print(f"Error: 项目文件格式无效，已从备份恢复", file=sys.stderr)
                    return False

            # 删除备份
            if backup_path.exists():
                backup_path.unlink()

            self.logger.info(f"Project saved successfully: {self.xcodeproj_path}")
            print(f"✓ 项目已保存: {self.xcodeproj_path}")
            return True

        except Exception as e:
            self.logger.exception(f"Failed to save project: {e}")
            # 尝试从备份恢复
            if backup_path.exists():
                try:
                    import shutil
                    shutil.copy2(backup_path, pbxproj_path)
                    self.logger.info("Restored from backup after exception")
                except Exception:
                    pass
            print(f"Error: 保存项目失败: {e}", file=sys.stderr)
            return False

    def copy_config(self, dry_run: bool = False) -> bool:
        """复制配置文件到项目目录（传入路径的父目录）"""
        self.logger.info("Copying config file...")
        print("正在检查配置文件...")

        # 使用传入路径的父目录，而不是解析出的 xcodeproj 的父目录
        # 这样可以正确处理 .xcworkspace 和 .xcodeproj 的情况
        if self.project_path.suffix in ['.xcworkspace', '.xcodeproj']:
            config_dir = self.project_path.parent
        else:
            config_dir = self.project_path
        config_dest = config_dir / '.biliobjclint.yaml'
        config_src = self.lint_path / 'config' / 'default.yaml'

        self.logger.info(f"Config source: {config_src}")
        self.logger.info(f"Config destination: {config_dest}")
        print(f"  配置文件目标路径: {config_dest}")

        if config_dest.exists():
            self.logger.info(f"Config file already exists: {config_dest}")
            print(f"✓ 配置文件已存在: {config_dest}")
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

    def _copy_script(self, source_name: str, target_scripts_dir: Path, dry_run: bool = False) -> bool:
        """复制脚本到目标 scripts 目录"""
        self.logger.info(f"Copying {source_name} to: {target_scripts_dir}")

        # 源文件位置
        # 调试模式：从本地开发目录复制
        # 正常模式：从 brew prefix 复制（bootstrap.sh 和 code_style_check.sh 在 config 目录）
        if self.debug_path:
            source_path = self.debug_path / "config" / source_name
            self.logger.info(f"[DEBUG MODE] Using local source: {source_path}")
        else:
            source_path = self.lint_path / "config" / source_name
        target_path = target_scripts_dir / source_name

        self.logger.debug(f"Source: {source_path}")
        self.logger.debug(f"Target: {target_path}")

        if not source_path.exists():
            self.logger.error(f"Source {source_name} not found: {source_path}")
            print(f"Error: 源文件不存在: {source_path}", file=sys.stderr)
            return False

        if dry_run:
            self.logger.info(f"[DRY RUN] Would copy {source_name} to: {target_path}")
            print(f"[DRY RUN] 将复制 {source_name} 到: {target_path}")
            return True

        try:
            # 创建目录
            target_scripts_dir.mkdir(parents=True, exist_ok=True)

            # 复制文件
            shutil.copy2(source_path, target_path)

            # 设置执行权限
            target_path.chmod(
                target_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )

            self.logger.info(f"Successfully copied {source_name} to: {target_path}")
            print(f"✓ 已复制 {source_name} 到: {target_path}")
            return True

        except Exception as e:
            self.logger.exception(f"Failed to copy {source_name}: {e}")
            print(f"Error: 复制 {source_name} 失败: {e}", file=sys.stderr)
            return False

    def copy_bootstrap_script(self, target_scripts_dir: Path, dry_run: bool = False) -> bool:
        """复制 bootstrap.sh 到目标 scripts 目录"""
        return self._copy_script("bootstrap.sh", target_scripts_dir, dry_run)

    def copy_code_style_check_script(self, target_scripts_dir: Path, dry_run: bool = False) -> bool:
        """复制 code_style_check.sh 到目标 scripts 目录"""
        return self._copy_script("code_style_check.sh", target_scripts_dir, dry_run)

    def get_project_srcroot(self) -> Optional[Path]:
        """获取项目的 SRCROOT（即 .xcodeproj 的父目录）"""
        if not self.xcodeproj_path:
            return None
        return self.xcodeproj_path.parent

    def has_bootstrap_phase(self, target) -> bool:
        """检查是否已存在 Bootstrap Phase"""
        build_phases = target.buildPhases
        for phase_id in build_phases:
            phase = self.project.objects[phase_id]
            if phase.isa == 'PBXShellScriptBuildPhase':
                if hasattr(phase, 'name') and phase.name == BOOTSTRAP_PHASE_NAME:
                    return True
                # 也检查脚本内容
                if hasattr(phase, 'shellScript') and 'Package Manager' in str(phase.shellScript):
                    return True
        return False

    def _find_phase_index(self, target, phase_type: str = None, phase_name: str = None) -> int:
        """
        查找指定 Build Phase 的索引位置

        Args:
            target: Target 对象
            phase_type: Phase 类型，如 'PBXSourcesBuildPhase' (Compile Sources)
            phase_name: Phase 名称，如 '[BiliObjcLint] Package Manager'

        Returns:
            找到的索引位置，未找到返回 -1
        """
        build_phases = target.buildPhases
        for i, phase_id in enumerate(build_phases):
            phase = self.project.objects[phase_id]
            if phase_type and phase.isa == phase_type:
                return i
            if phase_name and hasattr(phase, 'name') and phase.name == phase_name:
                return i
        return -1

    def _get_compile_sources_index(self, target) -> int:
        """获取 Compile Sources 阶段的索引位置"""
        return self._find_phase_index(target, phase_type='PBXSourcesBuildPhase')

    def _get_bootstrap_phase_index(self, target) -> int:
        """获取 Package Manager 阶段的索引位置"""
        return self._find_phase_index(target, phase_name=BOOTSTRAP_PHASE_NAME)

    def _create_shell_script_phase(self, script_content: str, phase_name: str) -> str:
        """
        创建一个 Shell Script Build Phase 对象

        Args:
            script_content: 脚本内容
            phase_name: Phase 名称

        Returns:
            创建的 phase 的 ID
        """
        from pbxproj import PBXGenericObject
        from pbxproj.PBXKey import PBXKey

        # 生成唯一 ID
        import hashlib
        import time
        unique_str = f"{phase_name}{time.time()}"
        phase_id = hashlib.md5(unique_str.encode()).hexdigest()[:24].upper()

        # 创建 PBXShellScriptBuildPhase 对象
        phase_data = {
            'isa': 'PBXShellScriptBuildPhase',
            'buildActionMask': 2147483647,
            'files': [],
            'inputPaths': [],
            'name': phase_name,
            'outputPaths': [],
            'runOnlyForDeploymentPostprocessing': 0,
            'shellPath': '/bin/sh',
            'shellScript': script_content,
        }

        phase = PBXGenericObject().parse(phase_data)
        # 必须在添加到 project.objects 之前设置 _id，否则排序比较会失败
        phase._id = PBXKey(phase_id, self.project.objects)
        self.project.objects[phase_id] = phase

        return phase_id

    def _insert_phase_at_index(self, target, phase_id: str, index: int):
        """
        在指定位置插入 Build Phase

        Args:
            target: Target 对象
            phase_id: Phase ID
            index: 插入位置，0 表示最前面
        """
        from pbxproj.PBXKey import PBXKey

        build_phases = list(target.buildPhases)

        # 确保 index 在有效范围内
        if index < 0:
            index = 0
        if index > len(build_phases):
            index = len(build_phases)

        # 将 phase_id 转换为 PBXKey 对象（需要传入 parent）
        phase_key = PBXKey(phase_id, self.project.objects)
        build_phases.insert(index, phase_key)
        target.buildPhases = build_phases
        self.logger.debug(f"Inserted phase {phase_id} at index {index}")

    def add_bootstrap_phase(self, target, relative_scripts_path: str, dry_run: bool = False) -> bool:
        """
        添加 Bootstrap Build Phase

        注入位置：Build Phases 最前面（index 0），必须在 Compile Sources 之前
        """
        self.logger.info(f"Adding bootstrap phase to target: {target.name}")

        if self.has_bootstrap_phase(target):
            self.logger.info(f"Target '{target.name}' already has bootstrap phase")
            print(f"Target '{target.name}' 已存在 Bootstrap Phase")
            return True

        # 生成脚本内容
        scripts_path = "${SRCROOT}/" + relative_scripts_path
        script_content = BOOTSTRAP_SCRIPT_TEMPLATE.format(scripts_path=scripts_path)

        self.logger.debug(f"Scripts path in Build Phase: {scripts_path}")
        self.logger.debug(f"Generated script content ({len(script_content)} chars)")

        if dry_run:
            self.logger.info(f"[DRY RUN] Would add bootstrap phase to target '{target.name}'")
            print(f"[DRY RUN] 将为 Target '{target.name}' 添加 Bootstrap Phase:")
            print(f"  名称: {BOOTSTRAP_PHASE_NAME}")
            print(f"  位置: Build Phases 最前面 (index 0)")
            print(f"  脚本路径: {scripts_path}/bootstrap.sh")
            return True

        try:
            # 创建 Shell Script Build Phase
            phase_id = self._create_shell_script_phase(script_content, BOOTSTRAP_PHASE_NAME)

            # 插入到 Build Phases 最前面 (index 0)
            self._insert_phase_at_index(target, phase_id, 0)

            self.logger.info(f"Successfully added bootstrap phase to target '{target.name}' at index 0")
            print(f"✓ 已为 Target '{target.name}' 添加 Bootstrap Phase（位于 Build Phases 最前面）")
            return True

        except Exception as e:
            self.logger.exception(f"Failed to add bootstrap phase: {e}")
            print(f"Error: 添加 Bootstrap Phase 失败: {e}", file=sys.stderr)
            return False

    def do_bootstrap(self, target_name: Optional[str], dry_run: bool = False) -> bool:
        """执行 bootstrap 操作：复制脚本并注入 Build Phase"""
        self.logger.info("Executing bootstrap operation")
        if self.debug_path:
            self.logger.info(f"[DEBUG MODE] Debug path: {self.debug_path}")
            print(f"[DEBUG MODE] 启用调试模式，使用本地目录: {self.debug_path}")

        # 1. 确定 scripts 目录位置（输入路径的同级目录）
        scripts_dir = self.project_path.parent / "scripts"
        self.logger.debug(f"Target scripts directory: {scripts_dir}")

        # 2. 处理调试模式标记文件
        debug_file = scripts_dir / ".biliobjclint_debug"
        if self.debug_path:
            # 调试模式：创建标记文件
            if not dry_run:
                scripts_dir.mkdir(parents=True, exist_ok=True)
                debug_file.write_text(str(self.debug_path))
                self.logger.info(f"[DEBUG MODE] Created debug marker: {debug_file}")
                print(f"✓ 已创建调试标记文件: {debug_file}")
            else:
                print(f"[DRY RUN] 将创建调试标记文件: {debug_file}")
        else:
            # 非调试模式：删除标记文件（如果存在）
            if debug_file.exists() and not dry_run:
                debug_file.unlink()
                self.logger.info(f"Removed debug marker: {debug_file}")
                print(f"✓ 已移除调试标记文件（恢复正常模式）")

        # 3. 复制 bootstrap.sh
        if not self.copy_bootstrap_script(scripts_dir, dry_run):
            return False

        # 4. 复制 code_style_check.sh
        if not self.copy_code_style_check_script(scripts_dir, dry_run):
            return False

        # 6. 获取 target
        target = self.get_target(target_name)
        if not target:
            if target_name:
                self.logger.error(f"Target '{target_name}' not found")
                print(f"Error: Target '{target_name}' 不存在", file=sys.stderr)
                print("使用 --list-targets 查看可用的 Targets")
            else:
                self.logger.error("No available target found")
                print("Error: 未找到可用的 Target", file=sys.stderr)
            return False

        self.logger.info(f"Selected target: {target.name}")
        print(f"Target: {target.name}")

        # 7. 获取 SRCROOT 并计算相对路径
        srcroot = self.get_project_srcroot()
        if not srcroot:
            self.logger.error("Cannot determine SRCROOT")
            print("Error: 无法确定 SRCROOT", file=sys.stderr)
            return False

        relative_path = os.path.relpath(scripts_dir, srcroot)
        self.logger.debug(f"SRCROOT: {srcroot}")
        self.logger.debug(f"Relative path from SRCROOT to scripts: {relative_path}")
        print(f"SRCROOT: {srcroot}")
        print(f"Scripts 相对路径: {relative_path}")
        print()

        # 8. 保存完整项目配置到持久化存储
        # Key = normalize(xcodeproj_path)|target_name
        # 这样在 Xcode Build Phase 中可以通过 ${PROJECT_FILE_PATH} 和 ${TARGET_NAME} 构建 key
        if not dry_run:
            config = project_config.ProjectConfig(
                xcode_path=str(self.project_path),
                is_workspace=(self.project_path.suffix == '.xcworkspace'),
                xcodeproj_path=str(self.xcodeproj_path),
                project_name=self.project_name or self.xcodeproj_path.stem,
                target_name=target.name,
                scripts_dir_absolute=str(scripts_dir),
                scripts_dir_relative=relative_path
            )
            key = project_config.save(config)
            self.logger.info(f"Saved project config (key: {key})")

        # 9. 添加 Bootstrap Build Phase
        if not self.add_bootstrap_phase(target, relative_path, dry_run):
            return False

        # 10. 保存项目
        return self.save(dry_run)

    def show_manual(self) -> None:
        """显示手动配置说明（使用自动计算的路径）"""
        # 计算 scripts 目录相对于 SRCROOT 的路径
        scripts_dir = self.project_path.parent / "scripts"
        srcroot = self.get_project_srcroot()

        if srcroot:
            relative_path = os.path.relpath(scripts_dir, srcroot)
            scripts_path = "${SRCROOT}/" + relative_path
        else:
            # 默认值
            scripts_path = "${SRCROOT}/../scripts"

        print("")
        print("==========================================")
        print("     手动配置 Xcode Build Phase")
        print("==========================================")
        print("")
        print("推荐使用 --bootstrap 自动配置，或手动执行以下步骤：")
        print("")
        print("1. 创建 scripts 目录（与 .xcworkspace/.xcodeproj 同级）")
        print(f"   mkdir -p {scripts_dir}")
        print("")
        print("2. 复制脚本到 scripts 目录:")
        print("   BREW_PREFIX=$(brew --prefix biliobjclint)")
        print('   cp "$BREW_PREFIX/libexec/config/bootstrap.sh" scripts/')
        print('   cp "$BREW_PREFIX/libexec/config/code_style_check.sh" scripts/')
        print("   chmod +x scripts/*.sh")
        print("")
        print("3. 打开 Xcode 项目 → 选择 Target → Build Phases")
        print("")
        print("4. 添加 Package Manager Phase（点击 '+' → New Run Script Phase）:")
        print(f"   - 重命名为: {BOOTSTRAP_PHASE_NAME}")
        print("   - 拖动到 Build Phases 最前面")
        print("   - 粘贴脚本:")
        print("")
        print("----------------------------------------")
        print("#!/bin/bash")
        print(f'"{scripts_path}/bootstrap.sh" -w "${{WORKSPACE_PATH}}" -p "${{PROJECT_FILE_PATH}}" -t "${{TARGET_NAME}}"')
        print("----------------------------------------")
        print("")
        print("5. 添加 Code Style Lint Phase（点击 '+' → New Run Script Phase）:")
        print(f"   - 重命名为: {PHASE_NAME}")
        print("   - 放在 Package Manager 后面，Compile Sources 前面")
        print("   - 粘贴脚本:")
        print("")
        print("----------------------------------------")
        print("#!/bin/bash")
        print(f'"{scripts_path}/code_style_check.sh"')
        print("----------------------------------------")
        print("")
        print("6. 复制配置文件到项目根目录:")
        print("   BREW_PREFIX=$(brew --prefix biliobjclint)")
        print(f'   cp "$BREW_PREFIX/libexec/config/default.yaml" {self.project_path.parent}/.biliobjclint.yaml')
        print("")
        print(f"注意: 以上路径基于您的项目结构自动计算")
        print(f"      SRCROOT = {srcroot}")
        print(f"      Scripts 相对路径 = {relative_path if srcroot else '../scripts'}")
        print("")


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
        lint_path = str(Path(__file__).parent.parent)
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
