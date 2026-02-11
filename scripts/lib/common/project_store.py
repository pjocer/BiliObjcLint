#!/usr/bin/env python3
"""
项目配置统一存取模块

提供项目配置的存储、读取和运行时上下文管理。

存储位置：~/.biliobjclint/projects.json

Key 格式：{normalized_xcodeproj_path}|{target_name}
- xcodeproj_path: 规范化的 .xcodeproj 绝对路径
- target_name: Target 名称

架构：
- ProjectConfig: 项目配置数据结构
- ProjectStore: 多工程配置的 CRUD 操作（持久化存储）
- ProjectContext: 运行时的"当前上下文"单例（由 Xcode 环境变量决定）

使用方式：

    from lib.common.project_store import ProjectContext, ProjectStore

    # === Shell 入口脚本初始化（code_style_check.sh 调用的 Python 代码）===
    if not ProjectContext.init():
        print("Error: 项目配置不存在，请先执行 --bootstrap")
        sys.exit(1)

    # === 工具内部任何位置获取当前项目信息 ===
    ctx = ProjectContext.current()
    if ctx:
        print(f"project_key: {ctx.project_key}")
        print(f"project_root: {ctx.project_root}")

    # 或使用 require 版本（配置不存在会抛异常）
    ctx = ProjectContext.require()
    metrics_payload["project_key"] = ctx.project_key

    # === 管理多工程配置（bootstrap 时使用）===
    ProjectStore.save(config)
    ProjectStore.get(xcodeproj_path, target_name)
    ProjectStore.list_all()
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


# ==================== ProjectStore: 多工程配置 CRUD ====================


class ProjectStore:
    """
    项目配置存储类

    管理 ~/.biliobjclint/projects.json 中的多工程配置。
    支持多个 workspace/xcodeproj 的多个 target。
    """

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


# ==================== ProjectContext: 运行时上下文单例 ====================


class ProjectContext:
    """
    项目上下文单例

    在 Shell 入口脚本（bootstrap.sh / code_style_check.sh）调用的 Python 代码中初始化，
    之后在 Python 代码任何位置都可以通过 ProjectContext.current() 获取当前项目信息。

    每次 Xcode Build Phase 执行时，环境变量 PROJECT_FILE_PATH 和 TARGET_NAME
    指定了当前正在编译的是哪个工程的哪个 target。
    """

    _current: Optional['ProjectContext'] = None

    def __init__(self, config: ProjectConfig):
        self._config = config
        # 缓存从环境变量读取的值
        self._env_srcroot = os.environ.get("SRCROOT", "")
        self._env_configuration = os.environ.get("CONFIGURATION", "")

    # ==================== 初始化方法 ====================

    @classmethod
    def init(
        cls,
        xcodeproj_path: Optional[str] = None,
        target_name: Optional[str] = None
    ) -> bool:
        """
        初始化当前项目上下文

        从环境变量或参数读取 xcodeproj_path 和 target_name，
        然后从 projects.json 加载对应的配置。

        Args:
            xcodeproj_path: .xcodeproj 路径（可选，默认从 PROJECT_FILE_PATH 环境变量读取）
            target_name: Target 名称（可选，默认从 TARGET_NAME 环境变量读取）

        Returns:
            是否成功初始化
        """
        xcode_path = xcodeproj_path or os.environ.get("PROJECT_FILE_PATH", "")
        target = target_name or os.environ.get("TARGET_NAME", "")

        if not xcode_path or not target:
            return False

        config = ProjectStore.get(xcode_path, target)
        if not config:
            return False

        cls._current = cls(config)
        return True

    @classmethod
    def init_with_config(cls, config: ProjectConfig) -> None:
        """
        使用已有配置初始化上下文（用于 bootstrap 等场景）

        Args:
            config: 项目配置
        """
        cls._current = cls(config)

    @classmethod
    def reset(cls) -> None:
        """重置上下文（用于测试）"""
        cls._current = None

    # ==================== 获取上下文 ====================

    @classmethod
    def current(cls) -> Optional['ProjectContext']:
        """
        获取当前项目上下文

        如果未初始化，会尝试从环境变量自动初始化。

        Returns:
            当前项目上下文，如果未初始化且无法自动初始化则返回 None
        """
        if cls._current is None:
            cls.init()  # 尝试自动初始化
        return cls._current

    @classmethod
    def require(cls) -> 'ProjectContext':
        """
        获取当前项目上下文（必须存在）

        如果未初始化或配置不存在，抛出 RuntimeError。

        Returns:
            当前项目上下文

        Raises:
            RuntimeError: 上下文未初始化
        """
        ctx = cls.current()
        if ctx is None:
            raise RuntimeError(
                "Project context not initialized. "
                "Please run bootstrap first or check environment variables."
            )
        return ctx

    @classmethod
    def is_initialized(cls) -> bool:
        """检查上下文是否已初始化"""
        return cls._current is not None

    # ==================== 配置访问属性 ====================

    @property
    def config(self) -> ProjectConfig:
        """原始配置对象"""
        return self._config

    @property
    def project_key(self) -> str:
        """
        项目聚合 Key（用于 metrics 聚合）

        通常是 workspace 名称或项目目录名。
        """
        return self._config.project_key

    @property
    def project_name(self) -> str:
        """项目名称（从 workspace 中选择的项目，或 xcodeproj 的名称）"""
        return self._config.project_name

    @property
    def target_name(self) -> str:
        """Target 名称"""
        return self._config.target_name

    @property
    def is_workspace(self) -> bool:
        """是否是 workspace"""
        return self._config.is_workspace

    @property
    def xcode_path(self) -> Path:
        """Xcode 项目路径（.xcworkspace 或 .xcodeproj）"""
        return Path(self._config.xcode_path)

    @property
    def xcodeproj_path(self) -> Path:
        """解析出的 .xcodeproj 路径"""
        return Path(self._config.xcodeproj_path)

    # ==================== 路径相关属性 ====================

    @property
    def project_root(self) -> Path:
        """
        项目根目录

        优先从环境变量 SRCROOT 读取，否则从配置推断。
        """
        if self._env_srcroot:
            return Path(self._env_srcroot).resolve()
        return Path(self._config.xcodeproj_path).parent.resolve()

    @property
    def scripts_dir(self) -> Path:
        """scripts 目录绝对路径"""
        return Path(self._config.scripts_dir_absolute)

    @property
    def scripts_dir_relative(self) -> str:
        """scripts 目录相对于 SRCROOT 的路径"""
        return self._config.scripts_dir_relative

    @property
    def scripts_srcroot_path(self) -> str:
        """${SRCROOT}/xxx 格式的 scripts 路径（用于 Build Phase 脚本）"""
        return "${SRCROOT}/" + self._config.scripts_dir_relative

    @property
    def config_file(self) -> Path:
        """配置文件路径"""
        return self.scripts_dir / "config.yaml"

    # ==================== 环境变量相关属性 ====================

    @property
    def configuration(self) -> str:
        """构建配置（Debug/Release）"""
        return self._env_configuration

    @property
    def is_release(self) -> bool:
        """是否是 Release 构建"""
        return self._env_configuration == "Release"

    @property
    def is_debug(self) -> bool:
        """是否是 Debug 构建"""
        return self._env_configuration == "Debug"

    # ==================== 组合值方法 ====================

    def get_store_key(self) -> str:
        """获取在 projects.json 中的存储 key"""
        return make_key(self._config.xcodeproj_path, self._config.target_name)

    def get_log_prefix(self) -> str:
        """获取日志前缀"""
        return f"[{self.project_key}/{self.target_name}]"


# ==================== 便捷函数（基于 ProjectContext）====================


def get_project_key(fallback: str = "unknown") -> str:
    """
    获取当前项目的 project_key

    优先从 ProjectContext 获取，否则尝试从环境变量推断。

    Args:
        fallback: 无法获取时的默认值

    Returns:
        project_key 字符串
    """
    ctx = ProjectContext.current()
    if ctx:
        return ctx.project_key

    # Fallback: 从环境变量推断
    workspace_dir = os.environ.get("WORKSPACE_DIR", "")
    if workspace_dir:
        return Path(workspace_dir).stem

    project_name_env = os.environ.get("PROJECT_NAME", "")
    if project_name_env:
        return project_name_env

    return fallback


def get_project_name(fallback: str = "unknown") -> str:
    """
    获取当前项目的 project_name

    优先从 ProjectContext 获取，否则尝试从环境变量推断。

    Args:
        fallback: 无法获取时的默认值

    Returns:
        project_name 字符串
    """
    ctx = ProjectContext.current()
    if ctx:
        return ctx.project_name

    # Fallback: 从环境变量推断
    target_name_env = os.environ.get("TARGET_NAME", "")
    if target_name_env:
        return target_name_env

    return fallback


def get_project_root(fallback: Optional[str] = None) -> Optional[Path]:
    """
    获取当前项目的根目录

    优先从 ProjectContext 获取，否则尝试从环境变量推断。

    Args:
        fallback: 无法获取时的默认路径

    Returns:
        项目根目录的 Path 对象，如果无法确定返回 None
    """
    ctx = ProjectContext.current()
    if ctx:
        return ctx.project_root

    # Fallback: 从环境变量推断
    srcroot = os.environ.get("SRCROOT", "")
    if srcroot:
        return Path(srcroot).resolve()

    if fallback:
        return Path(fallback).resolve()

    return None
