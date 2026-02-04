"""
XcodeIntegrator 主类

组合所有 Mixin 类，提供完整的 Xcode 项目集成功能。
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from pbxproj import XcodeProject

# 添加 scripts 目录到路径
SCRIPT_DIR = Path(__file__).parent
SCRIPTS_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.lint.logger import get_logger

from .templates import PHASE_NAME, BOOTSTRAP_PHASE_NAME, SCRIPT_VERSION
from .project_loader import ProjectLoaderMixin
from .phase_manager import PhaseManagerMixin
from .bootstrap import BootstrapMixin


class XcodeIntegrator(ProjectLoaderMixin, PhaseManagerMixin, BootstrapMixin):
    """Xcode 项目集成器"""

    def __init__(
        self,
        project_path: str,
        lint_path: str,
        project_name: Optional[str] = None,
        debug_path: Optional[str] = None
    ):
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
                    shutil.copy2(backup_path, pbxproj_path)
                    self.logger.info("Restored from backup after exception")
                except Exception:
                    pass
            print(f"Error: 保存项目失败: {e}", file=sys.stderr)
            return False

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
            relative_path = '../scripts'

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
        print(f"      Scripts 相对路径 = {relative_path}")
        print("")
