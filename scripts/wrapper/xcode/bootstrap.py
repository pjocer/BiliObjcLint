"""
Bootstrap 相关操作模块

处理 bootstrap.sh 和 code_style_check.sh 的复制，以及 Bootstrap Phase 的注入。
"""
import os
import sys
import shutil
import stat
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .templates import BOOTSTRAP_PHASE_NAME, BOOTSTRAP_SCRIPT_TEMPLATE

if TYPE_CHECKING:
    from .integrator import XcodeIntegrator


class BootstrapMixin:
    """Bootstrap 相关的 Mixin 类"""

    def has_bootstrap_phase(self: "XcodeIntegrator", target) -> bool:
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

    def add_bootstrap_phase(
        self: "XcodeIntegrator",
        target,
        relative_scripts_path: str,
        dry_run: bool = False
    ) -> bool:
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

    def _copy_script(
        self: "XcodeIntegrator",
        source_name: str,
        target_scripts_dir: Path,
        dry_run: bool = False
    ) -> bool:
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

    def copy_bootstrap_script(
        self: "XcodeIntegrator",
        target_scripts_dir: Path,
        dry_run: bool = False
    ) -> bool:
        """复制 bootstrap.sh 到目标 scripts 目录"""
        return self._copy_script("bootstrap.sh", target_scripts_dir, dry_run)

    def copy_code_style_check_script(
        self: "XcodeIntegrator",
        target_scripts_dir: Path,
        dry_run: bool = False
    ) -> bool:
        """复制 code_style_check.sh 到目标 scripts 目录"""
        return self._copy_script("code_style_check.sh", target_scripts_dir, dry_run)

    def copy_config(self: "XcodeIntegrator", dry_run: bool = False) -> bool:
        """复制配置文件到 .biliobjclint 目录"""
        self.logger.info("Copying config file...")
        print("正在检查配置文件...")

        # 使用传入路径的父目录，而不是解析出的 xcodeproj 的父目录
        # 这样可以正确处理 .xcworkspace 和 .xcodeproj 的情况
        if self.project_path.suffix in ['.xcworkspace', '.xcodeproj']:
            project_dir = self.project_path.parent
        else:
            project_dir = self.project_path
        # 配置文件放在 .biliobjclint 目录内
        scripts_dir = project_dir / '.biliobjclint'
        config_dest = scripts_dir / 'config.yaml'
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
            # 确保目录存在
            scripts_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config_src, config_dest)
            self.logger.info(f"Config file copied to: {config_dest}")
            print(f"✓ 配置文件已复制: {config_dest}")
            return True
        except Exception as e:
            self.logger.exception(f"Failed to copy config: {e}")
            print(f"Error: 复制配置文件失败: {e}", file=sys.stderr)
            return False

    def do_bootstrap(
        self: "XcodeIntegrator",
        target_name: Optional[str],
        dry_run: bool = False
    ) -> bool:
        """执行 bootstrap 操作：复制脚本并注入 Build Phase"""
        # 延迟导入避免循环
        from lib.common.project_store import ProjectConfig, ProjectStore

        self.logger.info("Executing bootstrap operation")
        if self.debug_path:
            self.logger.info(f"[DEBUG MODE] Debug path: {self.debug_path}")
            print(f"[DEBUG MODE] 启用调试模式，使用本地目录: {self.debug_path}")

        # 1. 确定 .biliobjclint 目录位置（输入路径的同级目录）
        scripts_dir = self.project_path.parent / ".biliobjclint"
        self.logger.debug(f"Target scripts directory: {scripts_dir}")

        # 2. 处理调试模式标记文件
        debug_file = scripts_dir / "debug"
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

        # 5. 复制配置文件（如果不存在）
        if not self.copy_config(dry_run):
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
            config = ProjectConfig(
                xcode_path=str(self.project_path),
                is_workspace=(self.project_path.suffix == '.xcworkspace'),
                xcodeproj_path=str(self.xcodeproj_path),
                project_name=self.project_name or self.xcodeproj_path.stem,
                target_name=target.name,
                scripts_dir_absolute=str(scripts_dir),
                scripts_dir_relative=relative_path
            )
            key = ProjectStore.save(config)
            self.logger.info(f"Saved project config (key: {key})")

        # 9. 添加 Bootstrap Build Phase
        if not self.add_bootstrap_phase(target, relative_path, dry_run):
            return False

        # 10. 保存项目
        return self.save(dry_run)
