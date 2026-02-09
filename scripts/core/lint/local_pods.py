"""
Local Pods Module - 本地 Pod 依赖检测
"""
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Set, List, Optional

from lib.logger import get_logger


class LocalPodsAnalyzer:
    """分析本地 Pod 依赖并检测变更"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.podfile_lock = self.project_root / "Podfile.lock"
        self._local_pods_cache: Optional[Dict[str, Path]] = None
        self.logger = get_logger("biliobjclint")

    def get_local_pods(self) -> Dict[str, Path]:
        """
        解析 Podfile.lock 获取本地 Pod 映射

        Returns:
            {"PodA": Path("/absolute/path/to/PodA"), ...}
        """
        if self._local_pods_cache is not None:
            return self._local_pods_cache

        if not self.podfile_lock.exists():
            self.logger.debug("Podfile.lock not found")
            return {}

        try:
            local_pods = self._parse_podfile_lock()
            self._local_pods_cache = local_pods
            self.logger.debug(f"Found {len(local_pods)} local pods: {list(local_pods.keys())}")
            return local_pods
        except Exception as e:
            self.logger.warning(f"Failed to parse Podfile.lock: {e}")
            return {}

    def _parse_podfile_lock(self) -> Dict[str, Path]:
        """
        解析 Podfile.lock 提取本地 Pod 路径

        Podfile.lock 格式示例:
        EXTERNAL SOURCES:
          PodA:
            :path: "/absolute/path/to/PodA"
          PodB:
            :path: "../relative/path/to/PodB"
        """
        local_pods = {}

        with open(self.podfile_lock, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取 EXTERNAL SOURCES 部分
        external_match = re.search(
            r'EXTERNAL SOURCES:\s*\n((?:  \S.*\n(?:    .*\n)*)*)',
            content
        )

        if not external_match:
            return {}

        external_section = external_match.group(1)

        # 解析每个 pod
        # 匹配格式：
        #   PodName:
        #     :path: "path/to/pod"
        pod_pattern = re.compile(
            r'^  (\S+):\s*\n((?:    .*\n)*)',
            re.MULTILINE
        )

        path_pattern = re.compile(r':path:\s*["\']?([^"\']+)["\']?')

        for pod_match in pod_pattern.finditer(external_section):
            pod_name = pod_match.group(1)
            pod_config = pod_match.group(2)

            path_match = path_pattern.search(pod_config)
            if path_match:
                path_str = path_match.group(1).strip()

                # 处理相对路径
                if not os.path.isabs(path_str):
                    pod_path = (self.project_root / path_str).resolve()
                else:
                    pod_path = Path(path_str).resolve()

                if pod_path.exists():
                    local_pods[pod_name] = pod_path
                else:
                    self.logger.debug(f"Local pod path not found: {pod_path}")

        return local_pods

    def is_git_repo(self, path: Path) -> bool:
        """检查路径是否是 git 仓库"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                cwd=path,
                capture_output=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_git_root(self, path: Path) -> Optional[Path]:
        """获取 git 仓库根目录"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                cwd=path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return Path(result.stdout.strip())
        except Exception:
            pass
        return None

    def get_changed_files(self, pod_path: Path, pod_name: str,
                          extensions: List[str], incremental: bool = True) -> List[str]:
        """
        获取本地 Pod 中的变更文件

        Args:
            pod_path: Pod 目录路径
            pod_name: Pod 名称
            extensions: 文件扩展名列表
            incremental: 是否增量检测

        Returns:
            文件绝对路径列表
        """
        if incremental and self.is_git_repo(pod_path):
            files = self._get_git_changed_files(pod_path, extensions)
            self.logger.debug(f"[{pod_name}] Git incremental: {len(files)} changed files")
        else:
            files = self._get_all_files(pod_path, extensions)
            self.logger.debug(f"[{pod_name}] Full scan: {len(files)} files")

        return files

    def _get_git_changed_files(self, pod_path: Path, extensions: List[str]) -> List[str]:
        """从 git 仓库获取变更文件"""
        git_root = self.get_git_root(pod_path) or pod_path

        try:
            # 获取未提交的变更 (unstaged)
            cmd_uncommitted = ['git', 'diff', '--name-only']
            result_uncommitted = subprocess.run(
                cmd_uncommitted,
                cwd=git_root,
                capture_output=True,
                text=True
            )
            uncommitted_files = result_uncommitted.stdout.strip().split('\n') if result_uncommitted.stdout.strip() else []

            # 获取 staged 变更
            cmd_staged = ['git', 'diff', '--name-only', '--cached']
            result_staged = subprocess.run(
                cmd_staged,
                cwd=git_root,
                capture_output=True,
                text=True
            )
            staged_files = result_staged.stdout.strip().split('\n') if result_staged.stdout.strip() else []

            # 获取未追踪的新文件
            cmd_untracked = ['git', 'ls-files', '--others', '--exclude-standard']
            result_untracked = subprocess.run(
                cmd_untracked,
                cwd=git_root,
                capture_output=True,
                text=True
            )
            untracked_files = result_untracked.stdout.strip().split('\n') if result_untracked.stdout.strip() else []

            # 合并所有变更文件
            all_files = set(uncommitted_files + staged_files + untracked_files)
            all_files.discard('')

            # 过滤扩展名并构建绝对路径
            filtered_files = []
            for f in all_files:
                if any(f.endswith(ext) for ext in extensions):
                    full_path = git_root / f
                    if full_path.exists():
                        # 确保文件在 pod_path 目录下
                        try:
                            full_path.relative_to(pod_path)
                            filtered_files.append(str(full_path))
                        except ValueError:
                            # 文件不在 pod_path 下，跳过
                            pass

            return filtered_files

        except subprocess.CalledProcessError:
            return []

    def _get_all_files(self, pod_path: Path, extensions: List[str]) -> List[str]:
        """获取目录下所有匹配文件"""
        files = []
        for ext in extensions:
            pattern = f"*{ext}"
            files.extend(str(p) for p in pod_path.rglob(pattern) if p.is_file())
        return files

    def get_changed_lines(self, file_path: str) -> Set[int]:
        """
        获取本地 Pod 文件中的变更行号

        Args:
            file_path: 文件绝对路径

        Returns:
            变更行号集合（空集合表示全量检查）
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return set()

        # 查找文件所属的 git 仓库
        git_root = self.get_git_root(file_path.parent)
        if not git_root:
            # 不是 git 仓库，返回空集合（表示检查所有行）
            return set()

        try:
            rel_path = file_path.relative_to(git_root)
        except ValueError:
            return set()

        changed_lines = set()

        try:
            # 获取未提交的变更
            cmd_uncommitted = ['git', 'diff', '-U0', '--', str(rel_path)]
            result_uncommitted = subprocess.run(
                cmd_uncommitted,
                cwd=git_root,
                capture_output=True,
                text=True
            )
            changed_lines.update(self._parse_diff_lines(result_uncommitted.stdout))

            # 获取 staged 变更
            cmd_staged = ['git', 'diff', '-U0', '--cached', '--', str(rel_path)]
            result_staged = subprocess.run(
                cmd_staged,
                cwd=git_root,
                capture_output=True,
                text=True
            )
            changed_lines.update(self._parse_diff_lines(result_staged.stdout))

        except subprocess.CalledProcessError:
            pass

        return changed_lines

    def _parse_diff_lines(self, diff_output: str) -> Set[int]:
        """
        解析 diff 输出，提取变更行号

        diff -U0 输出格式: @@ -old_start,old_count +new_start,new_count @@
        """
        changed_lines = set()

        pattern = r'@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@'

        for match in re.finditer(pattern, diff_output):
            start_line = int(match.group(1))
            count = int(match.group(2)) if match.group(2) else 1

            # count 为 0 表示删除操作，跳过
            if count == 0:
                continue

            for line in range(start_line, start_line + count):
                changed_lines.add(line)

        return changed_lines

    def get_pod_for_file(self, file_path: str) -> Optional[str]:
        """
        获取文件所属的本地 Pod 名称

        Args:
            file_path: 文件绝对路径

        Returns:
            Pod 名称，如果不属于任何本地 Pod 则返回 None
        """
        file_path = Path(file_path).resolve()
        local_pods = self.get_local_pods()

        for pod_name, pod_path in local_pods.items():
            try:
                file_path.relative_to(pod_path)
                return pod_name
            except ValueError:
                continue

        return None
