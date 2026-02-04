#!/usr/bin/env python3
"""
项目配置持久化模块

提供项目配置的存储和读取功能。

存储位置：~/.biliobjclint/projects.json

Key 格式：{normalized_xcodeproj_path}|{target_name}
- xcodeproj_path: 规范化的 .xcodeproj 绝对路径
- target_name: Target 名称

这个 Key 可以在 Xcode Build Phase 中通过 ${PROJECT_FILE_PATH} 和 ${TARGET_NAME} 构建。
"""
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


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

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


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


def get_scripts_srcroot_path(config: ProjectConfig) -> str:
    """
    获取 scripts 目录的 ${SRCROOT}/xxx 格式路径

    Args:
        config: 项目配置

    Returns:
        ${SRCROOT}/xxx 格式的路径
    """
    return "${SRCROOT}/" + config.scripts_dir_relative


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
