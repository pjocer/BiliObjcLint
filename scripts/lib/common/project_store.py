#!/usr/bin/env python3
"""
项目配置统一存取模块

提供项目配置的存储、读取和验证功能。

存储位置：~/.biliobjclint/projects.json

Key 格式：{normalized_xcodeproj_path}|{target_name}
- xcodeproj_path: 规范化的 .xcodeproj 绝对路径
- target_name: Target 名称

这个 Key 可以在 Xcode Build Phase 中通过 ${PROJECT_FILE_PATH} 和 ${TARGET_NAME} 构建。

使用方式：
    from lib.common import project_store

    # 获取 project_key 和 project_name（自动从环境变量或 projects.json 读取）
    project_key = project_store.get_project_key()
    project_name = project_store.get_project_name()

    # 验证配置是否存在（在脚本开始时调用）
    config = project_store.ensure_config()
    if not config:
        sys.exit(1)

    # 保存配置
    project_store.ProjectStore.save(config)
"""
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


# 配置存储文件
CONFIG_STORE = Path.home() / '.biliobjclint' / 'projects.json'


@dataclass
class ProjectConfig:
    """项目配置数据结构"""
    # 传入的 Xcode 路径（可能是 .xcworkspace 或 .xcodeproj）
    xcode_path: str
    # 是否是 workspace
    is_workspace: bool
    # 解析出的 .xcodeproj 路径
    xcodeproj_path: str
    # 项目名称（从 workspace 中选择的项目，或 xcodeproj 的名称）
    project_name: str
    # Target 名称
    target_name: str
    # scripts 目录绝对路径
    scripts_dir_absolute: str
    # scripts 目录相对于 SRCROOT 的路径
    scripts_dir_relative: str
    # 创建时间
    created_at: str = ""
    # project_key（用于 metrics 聚合，通常是 workspace 名称）
    project_key: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        # 如果没有设置 project_key，从 xcode_path 推断
        if not self.project_key:
            # 优先使用 workspace 目录名，否则使用 xcodeproj 目录名
            if self.is_workspace:
                self.project_key = Path(self.xcode_path).stem
            else:
                self.project_key = Path(self.xcodeproj_path).parent.name


def normalize_path(path: str) -> str:
    """
    规范化路径：解析符号链接、去除尾部斜杠、转换为绝对路径

    Args:
        path: 原始路径

    Returns:
        规范化后的路径字符串
    """
    try:
        return str(Path(path).resolve())
    except Exception:
        # 如果路径无效，至少去除尾部斜杠
        return path.rstrip('/')


def make_key(xcodeproj_path: str, target_name: str) -> str:
    """
    生成配置存储的 Key

    Key 格式：{normalized_xcodeproj_path}|{target_name}

    这个格式可以在 Xcode Build Phase 中通过以下方式构建：
    - xcodeproj_path = ${PROJECT_FILE_PATH}
    - target_name = ${TARGET_NAME}

    Args:
        xcodeproj_path: .xcodeproj 路径
        target_name: Target 名称

    Returns:
        格式化的 key 字符串
    """
    normalized_path = normalize_path(xcodeproj_path)
    return f"{normalized_path}|{target_name}"


class ProjectStore:
    """项目配置存储类"""

    @staticmethod
    def save(config: ProjectConfig) -> str:
        """
        保存项目配置到持久化存储

        Args:
            config: 项目配置

        Returns:
            生成的 key
        """
        CONFIG_STORE.parent.mkdir(parents=True, exist_ok=True)

        # 读取现有数据
        data: Dict[str, Any] = {}
        if CONFIG_STORE.exists():
            try:
                data = json.loads(CONFIG_STORE.read_text())
            except Exception:
                pass

        # 生成 key 并保存
        key = make_key(config.xcodeproj_path, config.target_name)
        data[key] = asdict(config)

        # 写入文件
        CONFIG_STORE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

        return key

    @staticmethod
    def get(xcodeproj_path: str, target_name: str) -> Optional[ProjectConfig]:
        """
        从持久化存储获取项目配置

        Args:
            xcodeproj_path: .xcodeproj 路径（对应 Xcode 的 ${PROJECT_FILE_PATH}）
            target_name: Target 名称（对应 Xcode 的 ${TARGET_NAME}）

        Returns:
            项目配置，如果不存在返回 None
        """
        if not CONFIG_STORE.exists():
            return None

        try:
            data = json.loads(CONFIG_STORE.read_text())
            key = make_key(xcodeproj_path, target_name)
            config_dict = data.get(key)
            if config_dict:
                return ProjectConfig(**config_dict)
            return None
        except Exception:
            return None

    @staticmethod
    def get_from_env() -> Optional[ProjectConfig]:
        """
        从环境变量获取项目配置

        使用 ${PROJECT_FILE_PATH} 和 ${TARGET_NAME} 构建 key

        Returns:
            项目配置，如果不存在返回 None
        """
        xcodeproj_path = os.environ.get("PROJECT_FILE_PATH", "")
        target_name = os.environ.get("TARGET_NAME", "")

        if not xcodeproj_path or not target_name:
            return None

        return ProjectStore.get(xcodeproj_path, target_name)

    @staticmethod
    def delete(xcodeproj_path: str, target_name: str) -> bool:
        """
        删除项目配置

        Args:
            xcodeproj_path: .xcodeproj 路径
            target_name: Target 名称

        Returns:
            是否成功删除
        """
        if not CONFIG_STORE.exists():
            return False

        try:
            data = json.loads(CONFIG_STORE.read_text())
            key = make_key(xcodeproj_path, target_name)
            if key in data:
                del data[key]
                CONFIG_STORE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def list_all() -> Dict[str, ProjectConfig]:
        """
        列出所有已保存的项目配置

        Returns:
            key -> ProjectConfig 的字典
        """
        if not CONFIG_STORE.exists():
            return {}

        try:
            data = json.loads(CONFIG_STORE.read_text())
            result = {}
            for key, config_dict in data.items():
                try:
                    result[key] = ProjectConfig(**config_dict)
                except Exception:
                    pass
            return result
        except Exception:
            return {}

    @staticmethod
    def get_scripts_srcroot_path(config: ProjectConfig) -> str:
        """
        获取 scripts 目录的 ${SRCROOT}/xxx 格式路径

        Args:
            config: 项目配置

        Returns:
            ${SRCROOT}/xxx 格式的路径
        """
        return "${SRCROOT}/" + config.scripts_dir_relative


def get_project_key(
    xcodeproj_path: Optional[str] = None,
    target_name: Optional[str] = None,
    fallback_root: Optional[Path] = None
) -> str:
    """
    获取 project_key

    优先级：
    1. 从 projects.json 读取（如果提供了 xcodeproj_path 和 target_name）
    2. 从环境变量 WORKSPACE_DIR 的末端路径名
    3. 从环境变量 PROJECT_NAME
    4. 使用 fallback_root 目录名

    Args:
        xcodeproj_path: .xcodeproj 路径（可选，默认从环境变量读取）
        target_name: Target 名称（可选，默认从环境变量读取）
        fallback_root: 兜底的项目根目录（可选）

    Returns:
        project_key 字符串
    """
    # 尝试从 projects.json 读取
    xcode_path = xcodeproj_path or os.environ.get("PROJECT_FILE_PATH", "")
    target = target_name or os.environ.get("TARGET_NAME", "")

    if xcode_path and target:
        config = ProjectStore.get(xcode_path, target)
        if config and config.project_key:
            return config.project_key

    # 从环境变量读取
    workspace_dir = os.environ.get("WORKSPACE_DIR", "")
    if workspace_dir:
        return Path(workspace_dir).stem  # 使用 .stem 获取不带扩展名的名称

    project_name_env = os.environ.get("PROJECT_NAME", "")
    if project_name_env:
        return project_name_env

    # 兜底
    if fallback_root:
        return fallback_root.name

    return "unknown"


def get_project_name(
    xcodeproj_path: Optional[str] = None,
    target_name: Optional[str] = None,
    fallback_root: Optional[Path] = None
) -> str:
    """
    获取 project_name

    优先级：
    1. 从 projects.json 读取的 target_name
    2. 从环境变量 TARGET_NAME
    3. 使用 fallback_root 目录名

    Args:
        xcodeproj_path: .xcodeproj 路径（可选）
        target_name: Target 名称（可选）
        fallback_root: 兜底的项目根目录（可选）

    Returns:
        project_name 字符串
    """
    # 尝试从 projects.json 读取
    xcode_path = xcodeproj_path or os.environ.get("PROJECT_FILE_PATH", "")
    target = target_name or os.environ.get("TARGET_NAME", "")

    if xcode_path and target:
        config = ProjectStore.get(xcode_path, target)
        if config:
            return config.target_name

    # 从环境变量读取
    target_name_env = os.environ.get("TARGET_NAME", "")
    if target_name_env:
        return target_name_env

    # 兜底
    if fallback_root:
        return fallback_root.name

    return "unknown"


def get_project_root(
    xcodeproj_path: Optional[str] = None,
    target_name: Optional[str] = None,
    fallback: Optional[str] = None
) -> Optional[Path]:
    """
    获取项目根目录（project_root）

    优先级：
    1. 从环境变量 SRCROOT 读取（Xcode Build Phase 环境）
    2. 从 projects.json 的 xcodeproj_path 推断（取其父目录）
    3. 使用 fallback 参数

    Args:
        xcodeproj_path: .xcodeproj 路径（可选，默认从环境变量读取）
        target_name: Target 名称（可选，默认从环境变量读取）
        fallback: 兜底路径（可选）

    Returns:
        项目根目录的 Path 对象，如果无法确定返回 None
    """
    # 1. 优先从环境变量 SRCROOT 读取
    srcroot = os.environ.get("SRCROOT", "")
    if srcroot:
        return Path(srcroot).resolve()

    # 2. 从 projects.json 推断
    xcode_path = xcodeproj_path or os.environ.get("PROJECT_FILE_PATH", "")
    target = target_name or os.environ.get("TARGET_NAME", "")

    if xcode_path and target:
        config = ProjectStore.get(xcode_path, target)
        if config:
            # xcodeproj_path 的父目录即为 project_root
            return Path(config.xcodeproj_path).parent.resolve()

    # 3. 使用 fallback
    if fallback:
        return Path(fallback).resolve()

    return None


def ensure_config(
    xcodeproj_path: Optional[str] = None,
    target_name: Optional[str] = None,
    auto_create: bool = False,
    **create_kwargs
) -> Optional[ProjectConfig]:
    """
    确保项目配置存在

    在脚本开始时调用，验证 projects.json 中是否有对应的配置。

    Args:
        xcodeproj_path: .xcodeproj 路径（可选，默认从环境变量读取）
        target_name: Target 名称（可选，默认从环境变量读取）
        auto_create: 如果配置不存在是否自动创建
        **create_kwargs: 创建配置时的额外参数

    Returns:
        ProjectConfig 如果存在或成功创建，否则返回 None
    """
    xcode_path = xcodeproj_path or os.environ.get("PROJECT_FILE_PATH", "")
    target = target_name or os.environ.get("TARGET_NAME", "")

    if not xcode_path or not target:
        return None

    # 尝试获取现有配置
    config = ProjectStore.get(xcode_path, target)
    if config:
        return config

    # 如果不存在且允许自动创建
    if auto_create and create_kwargs:
        config = ProjectConfig(
            xcode_path=create_kwargs.get("xcode_path", xcode_path),
            is_workspace=create_kwargs.get("is_workspace", False),
            xcodeproj_path=create_kwargs.get("xcodeproj_path", xcode_path),
            project_name=create_kwargs.get("project_name", Path(xcode_path).stem),
            target_name=target,
            scripts_dir_absolute=create_kwargs.get("scripts_dir_absolute", ""),
            scripts_dir_relative=create_kwargs.get("scripts_dir_relative", ""),
            project_key=create_kwargs.get("project_key", ""),
        )
        ProjectStore.save(config)
        return config

    return None


# ==================== 兼容性别名 ====================
# 为了兼容旧的 project_config 模块的调用方式

def save(config: ProjectConfig) -> str:
    """兼容性别名：保存配置"""
    return ProjectStore.save(config)


def get(xcodeproj_path: str, target_name: str) -> Optional[ProjectConfig]:
    """兼容性别名：获取配置"""
    return ProjectStore.get(xcodeproj_path, target_name)


def get_scripts_srcroot_path(config: ProjectConfig) -> str:
    """兼容性别名：获取 scripts 路径"""
    return ProjectStore.get_scripts_srcroot_path(config)


def delete(xcodeproj_path: str, target_name: str) -> bool:
    """兼容性别名：删除配置"""
    return ProjectStore.delete(xcodeproj_path, target_name)


def list_all() -> Dict[str, ProjectConfig]:
    """兼容性别名：列出所有配置"""
    return ProjectStore.list_all()
