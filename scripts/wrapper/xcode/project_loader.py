"""
Xcode 项目加载模块

处理 .xcworkspace 和 .xcodeproj 的加载和解析。
"""
import sys
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING
import xml.etree.ElementTree as ET

from pbxproj import XcodeProject

if TYPE_CHECKING:
    from .integrator import XcodeIntegrator


class ProjectLoaderMixin:
    """项目加载相关的 Mixin 类"""

    def load_project(self: "XcodeIntegrator") -> bool:
        """加载 Xcode 项目"""
        self.logger.info(f"Loading project: {self.project_path}")

        # 如果 xcodeproj_path 已设置（from_xcodeproj 场景），跳过路径解析
        if self.xcodeproj_path is None:
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

        self.logger.debug(f"Using xcodeproj: {self.xcodeproj_path}")

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

    def _get_projects_in_workspace(self: "XcodeIntegrator") -> List[Path]:
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

    def list_projects(self: "XcodeIntegrator") -> List[str]:
        """列出 workspace 中所有项目名称"""
        projects = self._get_projects_in_workspace()
        return [p.stem for p in projects]

    def _find_project_in_workspace(
        self: "XcodeIntegrator",
        project_name: Optional[str] = None
    ) -> Optional[Path]:
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

    def _find_project_in_directory(self: "XcodeIntegrator") -> Optional[Path]:
        """在目录中查找 .xcodeproj"""
        if self.project_path.is_dir():
            for item in self.project_path.iterdir():
                if item.suffix == '.xcodeproj':
                    return item
        return None

    def list_targets(self: "XcodeIntegrator") -> List[str]:
        """列出所有 Targets"""
        if not self.project:
            return []

        targets = []
        for target in self.project.objects.get_targets():
            targets.append(target.name)
        return targets

    def get_target(self: "XcodeIntegrator", target_name: Optional[str] = None):
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

    def get_project_srcroot(self: "XcodeIntegrator") -> Optional[Path]:
        """获取项目的 SRCROOT（即 .xcodeproj 的父目录）"""
        if not self.xcodeproj_path:
            return None
        return self.xcodeproj_path.parent
