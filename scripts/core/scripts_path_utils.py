#!/usr/bin/env python3
"""
scripts 路径持久化工具模块

提供 scripts 目录路径的存储、读取和计算功能。

存储格式：~/.biliobjclint/scripts_paths.json
Key: {project_path}|{project_name}|{target_name}
Value: scripts 相对于 SRCROOT 的路径
"""
import json
from pathlib import Path
from typing import Optional

# scripts_path 持久化存储文件
SCRIPTS_PATH_STORE = Path.home() / '.biliobjclint' / 'scripts_paths.json'


def make_key(project_path: str, project_name: Optional[str], target_name: str) -> str:
    """
    生成 scripts_path 存储的 key

    Args:
        project_path: 项目路径 (.xcworkspace 或 .xcodeproj)
        project_name: 项目名称（workspace 中的项目名，可能为空）
        target_name: Target 名称

    Returns:
        格式化的 key 字符串
    """
    return f"{project_path}|{project_name or ''}|{target_name}"


def save(project_path: str, project_name: Optional[str], target_name: str,
         relative_path: str) -> None:
    """
    保存 scripts 相对路径到持久化存储

    Args:
        project_path: 项目路径
        project_name: 项目名称
        target_name: Target 名称
        relative_path: scripts 相对于 SRCROOT 的路径
    """
    SCRIPTS_PATH_STORE.parent.mkdir(parents=True, exist_ok=True)

    # 读取现有数据
    data = {}
    if SCRIPTS_PATH_STORE.exists():
        try:
            data = json.loads(SCRIPTS_PATH_STORE.read_text())
        except Exception:
            pass

    # 更新数据
    key = make_key(project_path, project_name, target_name)
    data[key] = relative_path

    # 写入文件
    SCRIPTS_PATH_STORE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def get(project_path: str, project_name: Optional[str], target_name: str) -> Optional[str]:
    """
    从持久化存储获取 scripts 相对路径

    Args:
        project_path: 项目路径
        project_name: 项目名称
        target_name: Target 名称

    Returns:
        scripts 相对于 SRCROOT 的路径，如果不存在返回 None
    """
    if not SCRIPTS_PATH_STORE.exists():
        return None

    try:
        data = json.loads(SCRIPTS_PATH_STORE.read_text())
        key = make_key(project_path, project_name, target_name)
        return data.get(key)
    except Exception:
        return None


def get_srcroot_path(relative_path: str) -> str:
    """
    将相对路径转换为 ${SRCROOT}/xxx 格式

    Args:
        relative_path: scripts 相对于 SRCROOT 的路径

    Returns:
        ${SRCROOT}/xxx 格式的路径
    """
    return "${SRCROOT}/" + relative_path
