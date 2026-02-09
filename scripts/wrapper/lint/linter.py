"""
BiliObjCLint 主类模块

负责执行 lint 检查的核心逻辑。
"""
import argparse
import sys
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
import fnmatch

# 添加 scripts 目录到路径
SCRIPT_DIR = Path(__file__).parent
SCRIPTS_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.lint.config import ConfigLoader, LintConfig
from core.lint.git_diff import GitDiffAnalyzer, is_git_repo
from core.lint.reporter import Reporter, Violation, Severity
from core.lint.rule_engine import RuleEngine
from lib.logger import get_logger, LogContext
from lib.common import project_store
from core.lint.local_pods import LocalPodsAnalyzer
from core.lint.ignore_cache import IgnoreCache
from core.lint import metrics as metrics_mod


class BiliObjCLint:
    """BiliObjCLint 主类"""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.project_root = Path(args.project_root).resolve()
        self.config: Optional[LintConfig] = None
        self.raw_config: Dict[str, Dict] = {}
        self.reporter = Reporter(xcode_output=args.xcode_output)
        self.logger = get_logger("biliobjclint")
        self.start_time = time.time()
        self.run_id = str(uuid.uuid4())
        self.started_at_iso = datetime.now().astimezone().isoformat()
        # 本地 Pod 相关
        self.local_pods_analyzer: Optional[LocalPodsAnalyzer] = None
        self.file_to_pod_map: Dict[str, str] = {}  # file_path -> pod_name
        # 忽略缓存
        self.ignore_cache = IgnoreCache(project_root=str(self.project_root))

    def run(self) -> int:
        """执行 lint 检查，返回退出码"""
        self.logger.log_separator("BiliObjCLint Session Start")
        self.logger.info(f"Project root: {self.project_root}")
        self.logger.info(f"Incremental mode: {self.args.incremental}")
        self.logger.debug(f"Arguments: {vars(self.args)}")

        # 1. 加载配置
        with LogContext(self.logger, "config_loading"):
            self._load_config()

        # 2. 获取要检查的文件
        with LogContext(self.logger, "file_discovery"):
            files = self._get_files_to_check()

        if not files:
            self.logger.info("No files to check")
            if self.args.verbose:
                print("No files to check.", file=sys.stderr)
            return 0

        self.logger.info(f"Files to check: {len(files)}")
        self.logger.log_list("Files", files, level="debug")

        if self.args.verbose:
            print(f"Checking {len(files)} file(s)...", file=sys.stderr)
            for f in files[:10]:
                print(f"  - {f}", file=sys.stderr)
            if len(files) > 10:
                print(f"  ... and {len(files) - 10} more", file=sys.stderr)

        # 3. 获取变更行号（增量模式）
        changed_lines_map = {}
        if self.args.incremental:
            with LogContext(self.logger, "git_diff_analysis"):
                # 主工程文件
                main_project_files = [f for f in files if f not in self.file_to_pod_map]
                if main_project_files and is_git_repo(str(self.project_root)):
                    analyzer = GitDiffAnalyzer(str(self.project_root), self.config.base_branch)
                    changed_lines_map = analyzer.get_all_changed_lines_map(main_project_files)

                # 本地 Pod 文件
                if self.local_pods_analyzer:
                    local_pod_files = [f for f in files if f in self.file_to_pod_map]
                    for f in local_pod_files:
                        if self.config.local_pods.incremental:
                            # 增量模式：只检查变更行
                            changed_lines = self.local_pods_analyzer.get_changed_lines(f)
                            if changed_lines:
                                changed_lines_map[f] = changed_lines
                            else:
                                # 如果没有变更行信息（非 git 仓库或新文件），检查所有行
                                changed_lines_map[f] = set()
                        else:
                            # 全量模式：检查所有行（空集合表示不过滤）
                            changed_lines_map[f] = set()

                self.logger.debug(f"Changed lines map: {len(changed_lines_map)} files")

        # 4. 执行 Python 规则检查
        if not self.args.no_python_rules:
            with LogContext(self.logger, "python_rules_check"):
                python_violations = self._run_python_rules(files, changed_lines_map)
                self.reporter.add_violations(python_violations)
                self.logger.info(f"Python rules violations: {len(python_violations)}")

        # 5. 设置本地 Pod 信息
        if self.file_to_pod_map:
            for v in self.reporter.violations:
                if v.file_path in self.file_to_pod_map:
                    v.pod_name = self.file_to_pod_map[v.file_path]

        # 6. 过滤被忽略的违规
        with LogContext(self.logger, "ignore_filter"):
            before_ignore_count = len(self.reporter.violations)
            self._filter_ignored_violations()
            after_ignore_count = len(self.reporter.violations)
            if before_ignore_count != after_ignore_count:
                self.logger.info(f"Filtered {before_ignore_count - after_ignore_count} ignored violations")

        # 7. 过滤增量结果
        if self.args.incremental and changed_lines_map:
            before_count = len(self.reporter.violations)
            self.reporter.filter_by_changed_lines(changed_lines_map)
            after_count = len(self.reporter.violations)
            self.logger.debug(f"Incremental filter: {before_count} -> {after_count} violations")

        # 8. 输出结果
        elapsed = time.time() - self.start_time
        errors_count = sum(1 for v in self.reporter.violations if v.severity == Severity.ERROR)
        warnings_count = len(self.reporter.violations) - errors_count

        self.logger.info(f"Total violations: {len(self.reporter.violations)} (errors: {errors_count}, warnings: {warnings_count})")
        self.logger.info(f"Elapsed time: {elapsed:.2f}s")
        self.logger.log_separator("BiliObjCLint Session End")

        # 统一去重和排序（确保 JSON 输出、Xcode 输出、Metrics 上报数据一致）
        self.reporter.deduplicate()
        self.reporter.sort()

        # 如果指定了 --json-file，同时输出 JSON 到文件（用于 Claude fixer）
        if self.args.json_file:
            try:
                with open(self.args.json_file, 'w', encoding='utf-8') as f:
                    json_data = self.reporter.to_json(
                        run_id=self.run_id,
                        extra={
                            "created_at": self.started_at_iso,
                            "project": {
                                "key": project_store.get_project_key(fallback_root=self.project_root),
                                "name": project_store.get_project_name(fallback_root=self.project_root),
                            },
                        },
                    )
                    f.write(json_data)
                self.logger.debug(f"JSON output written to: {self.args.json_file}")
            except Exception as e:
                self.logger.warning(f"Failed to write JSON file: {e}")

        if self.args.json_output:
            print(self.reporter.to_json(run_id=self.run_id))
            return 1 if errors_count > 0 else 0
        else:
            exit_code = self.reporter.report()

            if self.args.verbose:
                self.reporter.print_summary()

            # 统计上报（不影响 lint 结果）
            try:
                if self.config and self.config.metrics.enabled:
                    # 获取规则的 display_name 和 description 映射
                    rule_display_info = RuleEngine.get_all_rule_display_names()
                    payload = metrics_mod.build_lint_payload(
                        run_id=self.run_id,
                        config=self.config,
                        raw_config=self.raw_config,
                        reporter=self.reporter,
                        project_root=self.project_root,
                        duration_ms=int(elapsed * 1000),
                        started_at_iso=self.started_at_iso,
                        rule_display_info=rule_display_info,
                    )
                    metrics_mod.send_payload(payload, self.config.metrics, self.logger)
            except Exception as e:
                self.logger.warning(f"Metrics send failed: {e}")

            return exit_code if self.config.fail_on_error else 0

    def _load_config(self):
        """加载配置文件"""
        config_path = self.args.config
        if config_path and not os.path.isabs(config_path):
            config_path = str(self.project_root / config_path)

        # 如果没有指定配置文件，尝试默认位置
        if not config_path or not os.path.exists(config_path):
            default_paths = [
                self.project_root / ".biliobjclint" / "config.yaml",  # 新位置（优先）
                self.project_root / ".biliobjclint.yaml",  # 旧位置（兼容）
                self.project_root / ".biliobjclint.yml",
                self.project_root / "biliobjclint.yaml",
            ]
            for p in default_paths:
                if p.exists():
                    config_path = str(p)
                    self.logger.debug(f"Found config file: {config_path}")
                    break

        if config_path:
            self.logger.info(f"Loading config from: {config_path}")
        else:
            self.logger.warning("No config file found, using defaults")

        loader = ConfigLoader(config_path)
        self.config = loader.load()
        self.raw_config = loader.get_raw_config()

        self.logger.debug(f"Config loaded: base_branch={self.config.base_branch}, fail_on_error={self.config.fail_on_error}")
        self.logger.debug(f"Included patterns: {self.config.included}")
        self.logger.debug(f"Excluded patterns: {self.config.excluded}")

        # 命令行参数覆盖配置
        if self.args.base_branch:
            self.config.base_branch = self.args.base_branch
            self.logger.debug(f"Base branch overridden to: {self.args.base_branch}")

    def _get_files_to_check(self) -> List[str]:
        """获取要检查的文件列表"""

        # 如果指定了具体文件
        if self.args.files:
            files = []
            for f in self.args.files:
                path = Path(f)
                if not path.is_absolute():
                    path = self.project_root / f
                if path.exists() and path.is_file():
                    files.append(str(path.resolve()))
            return files

        # 增量模式：获取 git 变更文件
        if self.args.incremental and is_git_repo(str(self.project_root)):
            analyzer = GitDiffAnalyzer(str(self.project_root), self.config.base_branch)
            files = analyzer.get_changed_files()
        else:
            # 全量模式：获取所有匹配文件
            files = self._find_all_files()

        # 应用 exclude 过滤
        files = self._filter_excluded(files)

        # 添加本地 Pod 文件
        if self.config.local_pods.enabled:
            local_pod_files = self._get_local_pod_files()
            files.extend(local_pod_files)

        # 去重（防止主工程和本地 Pod 文件重叠）
        return list(dict.fromkeys(files))

    def _get_local_pod_files(self) -> List[str]:
        """获取本地 Pod 中的文件"""
        self.local_pods_analyzer = LocalPodsAnalyzer(str(self.project_root))
        local_pods = self.local_pods_analyzer.get_local_pods()

        if not local_pods:
            return []

        files = []
        extensions = ['.m', '.mm', '.h']

        for pod_name, pod_path in local_pods.items():
            # 检查是否应该跳过此 Pod
            if not self._should_check_pod(pod_name):
                self.logger.debug(f"Skipping excluded pod: {pod_name}")
                continue

            # 增量检测条件：主工程增量模式 或 本地 Pod 配置增量模式
            use_incremental = self.args.incremental or self.config.local_pods.incremental

            # 获取 Pod 中的变更文件
            pod_files = self.local_pods_analyzer.get_changed_files(
                pod_path,
                pod_name,
                extensions,
                incremental=use_incremental
            )

            # 跳过没有变更文件的 Pod
            if not pod_files:
                self.logger.debug(f"Skipping pod with no changes: {pod_name}")
                continue

            # 记录文件到 Pod 的映射
            for f in pod_files:
                self.file_to_pod_map[f] = pod_name

            files.extend(pod_files)
            self.logger.info(f"Local pod [{pod_name}]: {len(pod_files)} files to check")

        return files

    def _should_check_pod(self, pod_name: str) -> bool:
        """判断是否应该检查此 Pod"""
        # 检查排除模式
        for pattern in self.config.local_pods.excluded_pods:
            if fnmatch.fnmatch(pod_name, pattern):
                return False

        # 检查包含模式（空表示所有）
        if self.config.local_pods.included_pods:
            for pattern in self.config.local_pods.included_pods:
                if fnmatch.fnmatch(pod_name, pattern):
                    return True
            return False

        return True

    def _filter_ignored_violations(self):
        """过滤被忽略的违规"""
        filtered = []
        for v in self.reporter.violations:
            # 必须有 code_hash 才能进行忽略检查
            if not v.code_hash:
                filtered.append(v)
                continue
            if not self.ignore_cache.is_ignored(v):
                filtered.append(v)
            else:
                self.logger.debug(f"Filtered ignored violation: {v.file_path}:{v.line} [{v.rule_id}]")
        self.reporter.violations = filtered

    def _find_all_files(self) -> List[str]:
        """查找所有匹配的文件"""
        files = []

        for pattern in self.config.included:
            # 支持 glob 模式
            # rglob 本身就是递归的，只需要提取文件名模式
            # "**/*.m" -> "*.m", "*/*.m" -> "*.m"
            if pattern.startswith("**/"):
                glob_pattern = pattern[3:]  # 去掉 "**/" 前缀
            elif pattern.startswith("*/"):
                glob_pattern = pattern[2:]  # 去掉 "*/" 前缀
            else:
                glob_pattern = pattern

            for path in self.project_root.rglob(glob_pattern):
                if path.is_file():
                    files.append(str(path.resolve()))

        return list(set(files))

    def _filter_excluded(self, files: List[str]) -> List[str]:
        """过滤排除的文件"""
        result = []

        for file_path in files:
            rel_path = str(Path(file_path).relative_to(self.project_root))

            excluded = False
            for pattern in self.config.excluded:
                if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(rel_path, pattern.rstrip("/*")):
                    excluded = True
                    break

            if not excluded:
                result.append(file_path)

        return result

    def _run_python_rules(self, files: List[str], changed_lines_map: dict) -> List[Violation]:
        """运行 Python 规则检查"""
        perf_config = self.config.performance

        engine = RuleEngine(
            str(self.project_root),
            parallel=perf_config.parallel,
            max_workers=perf_config.max_workers,
            file_cache_size_mb=perf_config.file_cache_size_mb
        )

        # 加载内置规则
        engine.load_builtin_rules(self.config.python_rules)
        self.logger.debug(f"Loaded {len(engine.rules)} builtin rules")

        # 加载自定义规则
        custom_path = self.config.custom_rules_python_path
        if custom_path:
            engine.load_custom_rules(custom_path)
            self.logger.debug(f"Loaded custom rules from: {custom_path}")

        rule_ids = [r.identifier for r in engine.rules]
        self.logger.info(f"Running {len(engine.rules)} Python rules: {rule_ids} (parallel={perf_config.parallel})")

        if self.args.verbose:
            mode_str = f"parallel ({perf_config.max_workers or 'auto'} workers)" if perf_config.parallel else "sequential"
            print(f"Running {len(engine.rules)} Python rules ({mode_str})...", file=sys.stderr)
            for rule in engine.rules:
                print(f"  - {rule.identifier}", file=sys.stderr)

        violations = engine.check_files(files, changed_lines_map)
        self.logger.debug(f"Python rules found {len(violations)} violations")
        return violations
