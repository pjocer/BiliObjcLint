"""
Git Diff Module - 增量检测变更文件和行号
"""
import subprocess
import re
from pathlib import Path
from typing import Dict, Set, List, Optional


class GitDiffAnalyzer:
    """分析 Git 变更，支持增量检查"""

    def __init__(self, project_root: str, base_branch: str = "origin/master"):
        self.project_root = Path(project_root)
        self.base_branch = base_branch
        self.git_root = self._get_git_root()

    def _get_git_root(self) -> Path:
        """获取 git 仓库根目录"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return Path(result.stdout.strip())
        except:
            pass
        return self.project_root

    def _should_check_committed(self) -> bool:
        """判断是否需要检查已提交的变更"""
        # 如果 base_branch 为空或为 HEAD，则只检查未提交的变更
        return bool(self.base_branch) and self.base_branch.upper() != 'HEAD'

    def get_changed_files(self, extensions: List[str] = None) -> List[str]:
        """
        获取变更的文件列表

        Args:
            extensions: 文件扩展名过滤，如 ['.m', '.h', '.mm']
        Returns:
            变更文件的绝对路径列表

        Note:
            - 如果 base_branch 为空或 "HEAD"，只检查未提交的变更
            - 如果设置了 base_branch（如 "origin/master"），则检查从分叉点到当前的所有变更
        """
        if extensions is None:
            extensions = ['.m', '.mm', '.h']

        try:
            committed_files = []

            # 只有设置了 base_branch 时，才检查已提交但未合并的变更
            if self._should_check_committed():
                cmd = ['git', 'diff', '--name-only', f'{self.base_branch}...HEAD']
                result = subprocess.run(
                    cmd,
                    cwd=self.git_root,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    committed_files = result.stdout.strip().split('\n') if result.stdout.strip() else []

            # 获取未提交的变更 (unstaged)
            cmd_uncommitted = ['git', 'diff', '--name-only']
            result_uncommitted = subprocess.run(
                cmd_uncommitted,
                cwd=self.git_root,
                capture_output=True,
                text=True
            )
            uncommitted_files = result_uncommitted.stdout.strip().split('\n') if result_uncommitted.stdout.strip() else []

            # 获取 staged 变更
            cmd_staged = ['git', 'diff', '--name-only', '--cached']
            result_staged = subprocess.run(
                cmd_staged,
                cwd=self.git_root,
                capture_output=True,
                text=True
            )
            staged_files = result_staged.stdout.strip().split('\n') if result_staged.stdout.strip() else []

            # 合并所有变更文件
            all_files = set(committed_files + uncommitted_files + staged_files)
            all_files.discard('')

            # 过滤扩展名，并只保留 project_root 目录下的文件
            filtered_files = []
            for f in all_files:
                if any(f.endswith(ext) for ext in extensions):
                    # 使用 git_root 构建完整路径
                    full_path = self.git_root / f
                    if full_path.exists():
                        # 检查文件是否在 project_root 目录下
                        try:
                            full_path.relative_to(self.project_root)
                            filtered_files.append(str(full_path))
                        except ValueError:
                            # 文件不在 project_root 下，跳过
                            pass

            return filtered_files

        except subprocess.CalledProcessError:
            return []

    def get_changed_lines(self, file_path: str) -> Set[int]:
        """
        获取文件中变更的行号

        Args:
            file_path: 文件绝对路径
        Returns:
            变更行号集合
        """
        changed_lines = set()
        # 使用 git_root 计算相对路径
        try:
            rel_path = Path(file_path).relative_to(self.git_root)
        except ValueError:
            # 文件不在 git 仓库中
            return changed_lines

        try:
            # 只有设置了 base_branch 时，才检查已提交但未合并的变更
            if self._should_check_committed():
                cmd = ['git', 'diff', '-U0', f'{self.base_branch}...HEAD', '--', str(rel_path)]
                result = subprocess.run(
                    cmd,
                    cwd=self.git_root,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    changed_lines.update(self._parse_diff_lines(result.stdout))

            # 获取未提交的变更 (unstaged)
            cmd_uncommitted = ['git', 'diff', '-U0', '--', str(rel_path)]
            result_uncommitted = subprocess.run(
                cmd_uncommitted,
                cwd=self.git_root,
                capture_output=True,
                text=True
            )
            changed_lines.update(self._parse_diff_lines(result_uncommitted.stdout))

            # 获取 staged 变更
            cmd_staged = ['git', 'diff', '-U0', '--cached', '--', str(rel_path)]
            result_staged = subprocess.run(
                cmd_staged,
                cwd=self.git_root,
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

        # 匹配 @@ -x,y +a,b @@ 格式
        pattern = r'@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@'

        for match in re.finditer(pattern, diff_output):
            start_line = int(match.group(1))
            count = int(match.group(2)) if match.group(2) else 1

            # 如果 count 为 0，表示删除操作，跳过
            if count == 0:
                continue

            for line in range(start_line, start_line + count):
                changed_lines.add(line)

        return changed_lines

    def get_all_changed_lines_map(self, files: List[str]) -> Dict[str, Set[int]]:
        """
        获取多个文件的变更行号映射

        Returns:
            {file_path: {line_numbers}}
        """
        result = {}
        for file_path in files:
            result[file_path] = self.get_changed_lines(file_path)
        return result


def is_git_repo(path: str) -> bool:
    """检查路径是否为 Git 仓库"""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            cwd=path,
            capture_output=True
        )
        return result.returncode == 0
    except:
        return False
