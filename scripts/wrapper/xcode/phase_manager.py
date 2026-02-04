"""
Build Phase 管理模块

处理 Build Phase 的添加、删除、查询等操作。
"""
import re
import sys
from typing import Optional, TYPE_CHECKING

from .templates import (
    PHASE_NAME,
    BOOTSTRAP_PHASE_NAME,
    LINT_SCRIPT_TEMPLATE,
    SCRIPT_VERSION,
)

if TYPE_CHECKING:
    from .integrator import XcodeIntegrator


class PhaseManagerMixin:
    """Build Phase 管理相关的 Mixin 类"""

    def has_lint_phase(self: "XcodeIntegrator", target) -> bool:
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

    def get_lint_phase_version(self: "XcodeIntegrator", target) -> Optional[str]:
        """获取已注入 Lint Phase 的版本号"""
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

    def check_update_needed(self: "XcodeIntegrator", target) -> tuple:
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

    def add_lint_phase(
        self: "XcodeIntegrator",
        target,
        dry_run: bool = False,
        override: bool = False,
        scripts_path: Optional[str] = None
    ) -> bool:
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
        # 延迟导入避免循环
        from core.lint import project_config

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

    def remove_lint_phase(self: "XcodeIntegrator", target, dry_run: bool = False) -> bool:
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

    def _find_phase_index(
        self: "XcodeIntegrator",
        target,
        phase_type: str = None,
        phase_name: str = None
    ) -> int:
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

    def _get_compile_sources_index(self: "XcodeIntegrator", target) -> int:
        """获取 Compile Sources 阶段的索引位置"""
        return self._find_phase_index(target, phase_type='PBXSourcesBuildPhase')

    def _get_bootstrap_phase_index(self: "XcodeIntegrator", target) -> int:
        """获取 Package Manager 阶段的索引位置"""
        return self._find_phase_index(target, phase_name=BOOTSTRAP_PHASE_NAME)

    def _create_shell_script_phase(
        self: "XcodeIntegrator",
        script_content: str,
        phase_name: str
    ) -> str:
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
        import hashlib
        import time

        # 生成唯一 ID
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

    def _insert_phase_at_index(
        self: "XcodeIntegrator",
        target,
        phase_id: str,
        index: int
    ):
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
