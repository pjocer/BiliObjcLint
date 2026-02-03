"""
Rule Engine Module - Python 规则引擎

支持:
- 文件内容缓存
- 多文件并行检查
- 规则结果缓存（持久化）
"""
import sys
import json
import importlib.util
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple, Any
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from .reporter import Violation, Severity
from .config import RuleConfig
from .logger import get_logger
from .file_cache import get_file_cache
from .result_cache import ResultCache


class BaseRule(ABC):
    """规则基类"""

    # 子类必须定义
    identifier: str = ""
    name: str = ""
    description: str = ""
    default_severity: str = "warning"

    def __init__(self, config: Optional[RuleConfig] = None):
        self.config = config or RuleConfig()
        self.severity = Severity(self.config.severity if self.config else self.default_severity)

    @property
    def enabled(self) -> bool:
        return self.config.enabled if self.config else True

    def get_param(self, key: str, default=None):
        """获取配置参数"""
        if self.config and self.config.params:
            return self.config.params.get(key, default)
        return default

    @abstractmethod
    def check(self, file_path: str, content: str, lines: List[str], changed_lines: Set[int]) -> List[Violation]:
        """
        执行规则检查

        Args:
            file_path: 文件路径
            content: 文件完整内容
            lines: 文件按行分割的列表
            changed_lines: 变更的行号集合（空集合表示检查全部）
        Returns:
            违规列表
        """
        pass

    def should_check_line(self, line_num: int, changed_lines: Set[int]) -> bool:
        """判断是否应该检查该行"""
        if not changed_lines:
            return True
        return line_num in changed_lines

    def create_violation(self, file_path: str, line: int, column: int, message: str,
                         related_lines: Optional[Tuple[int, int]] = None) -> Violation:
        """
        创建违规记录

        Args:
            file_path: 文件路径
            line: 违规行号
            column: 违规列号
            message: 违规消息
            related_lines: 关联行范围 (start, end)，用于增量过滤时判断是否保留
        """
        return Violation(
            file_path=file_path,
            line=line,
            column=column,
            severity=self.severity,
            message=message,
            rule_id=self.identifier,
            source='biliobjclint',
            related_lines=related_lines
        )


class RuleEngine:
    """规则引擎 - 管理和执行规则（性能优化版）"""

    def __init__(self, project_root: str, parallel: bool = True, max_workers: int = 0,
                 file_cache_size_mb: int = 100, result_cache_enabled: bool = True):
        """
        Args:
            project_root: 项目根目录
            parallel: 是否启用并行执行
            max_workers: 最大工作线程数（0 表示自动：min(32, cpu_count * 2)）
            file_cache_size_mb: 文件缓存最大容量（MB）
            result_cache_enabled: 是否启用规则结果缓存
        """
        self.project_root = Path(project_root)
        self.rules: List[BaseRule] = []
        self.logger = get_logger("biliobjclint")
        self.parallel = parallel
        self.max_workers = max_workers
        self._file_cache = get_file_cache(file_cache_size_mb)
        # 规则结果缓存
        cache_dir = self.project_root / ".biliobjclint_cache"
        self._result_cache = ResultCache(str(cache_dir), enabled=result_cache_enabled)
        self._config_hash: Optional[str] = None
        self.logger.debug(f"RuleEngine initialized: project_root={project_root}, parallel={parallel}, result_cache={result_cache_enabled}")

    def load_builtin_rules(self, rules_config: Dict[str, RuleConfig]):
        """加载内置规则"""
        self.logger.debug("Loading builtin rules...")

        # 动态导入 rules 模块
        scripts_dir = Path(__file__).parent.parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        from rules import get_all_rules

        loaded_count = 0
        for rule_class in get_all_rules():
            rule_id = rule_class.identifier
            config = rules_config.get(rule_id, RuleConfig())

            if config.enabled:
                rule = rule_class(config)
                self.rules.append(rule)
                loaded_count += 1
                self.logger.debug(f"Loaded rule: {rule_id} (severity={config.severity})")
            else:
                self.logger.debug(f"Skipped disabled rule: {rule_id}")

        self.logger.info(f"Loaded {loaded_count} builtin rules")

        # 计算配置 hash（用于结果缓存失效判断）
        config_dict = {k: {"enabled": v.enabled, "severity": v.severity, "params": v.params}
                       for k, v in rules_config.items()}
        self._config_hash = ResultCache.compute_config_hash(config_dict)
        self.logger.debug(f"Config hash: {self._config_hash}")

    def load_custom_rules(self, custom_rules_path: str):
        """加载自定义 Python 规则"""
        rules_dir = self.project_root / custom_rules_path
        self.logger.debug(f"Loading custom rules from: {rules_dir}")

        if not rules_dir.exists():
            self.logger.debug("Custom rules directory does not exist")
            return

        loaded_count = 0
        for py_file in rules_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            try:
                self._load_rule_from_file(py_file)
                loaded_count += 1
                self.logger.debug(f"Loaded custom rule from: {py_file.name}")
            except Exception as e:
                self.logger.warning(f"Failed to load custom rule {py_file}: {e}")
                print(f"Warning: Failed to load custom rule {py_file}: {e}", file=sys.stderr)

        self.logger.info(f"Loaded {loaded_count} custom rules")

    def _load_rule_from_file(self, file_path: Path):
        """从文件加载规则"""
        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        module = importlib.util.module_from_spec(spec)

        # 添加 scripts 目录到 path
        scripts_dir = self.project_root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        spec.loader.exec_module(module)

        # 查找 BaseRule 的子类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and
                issubclass(attr, BaseRule) and
                attr is not BaseRule and
                hasattr(attr, 'identifier') and
                attr.identifier):
                rule = attr()
                self.rules.append(rule)

    def check_file(self, file_path: str, changed_lines: Set[int] = None) -> List[Violation]:
        """
        对单个文件执行所有规则检查

        Args:
            file_path: 文件路径
            changed_lines: 变更行号集合（None 或空集合表示检查全部）
        Returns:
            违规列表
        """
        # 判断是否可以使用结果缓存
        # 只有全量检查（无 changed_lines）时才使用缓存
        use_result_cache = (not changed_lines) and self._config_hash

        # 尝试从结果缓存获取
        if use_result_cache:
            cached_violations = self._result_cache.get(file_path, self._config_hash)
            if cached_violations is not None:
                # 反序列化缓存的 violations
                return [self._deserialize_violation(v) for v in cached_violations]

        violations = []

        # 使用文件缓存读取文件内容
        cached = self._file_cache.get(file_path)
        if cached is None:
            return violations

        content, lines = cached

        for rule in self.rules:
            if not rule.enabled:
                continue

            try:
                rule_violations = rule.check(
                    file_path=file_path,
                    content=content,
                    lines=lines,
                    changed_lines=changed_lines or set()
                )
                violations.extend(rule_violations)
            except Exception as e:
                self.logger.warning(f"Rule {rule.identifier} failed on {file_path}: {e}")
                print(f"Warning: Rule {rule.identifier} failed on {file_path}: {e}", file=sys.stderr)

        # 存储到结果缓存
        if use_result_cache and violations is not None:
            serialized = [self._serialize_violation(v) for v in violations]
            self._result_cache.put(file_path, self._config_hash, serialized)

        return violations

    def _serialize_violation(self, v: Violation) -> Dict[str, Any]:
        """序列化 Violation 为 dict"""
        return {
            "file_path": v.file_path,
            "line": v.line,
            "column": v.column,
            "severity": v.severity.value,
            "message": v.message,
            "rule_id": v.rule_id,
            "source": v.source,
            "related_lines": v.related_lines
        }

    def _deserialize_violation(self, d: Dict[str, Any]) -> Violation:
        """反序列化 dict 为 Violation"""
        return Violation(
            file_path=d["file_path"],
            line=d["line"],
            column=d["column"],
            severity=Severity(d["severity"]),
            message=d["message"],
            rule_id=d["rule_id"],
            source=d.get("source", "biliobjclint"),
            related_lines=tuple(d["related_lines"]) if d.get("related_lines") else None
        )

    def check_files(self, files: List[str], changed_lines_map: Dict[str, Set[int]] = None) -> List[Violation]:
        """
        对多个文件执行检查（支持并行）

        Args:
            files: 文件路径列表
            changed_lines_map: {file_path: changed_lines_set}
        Returns:
            所有违规列表
        """
        self.logger.info(f"Checking {len(files)} files with {len(self.rules)} rules (parallel={self.parallel})")

        if not self.parallel or len(files) <= 1:
            violations = self._check_files_sequential(files, changed_lines_map)
        else:
            violations = self._check_files_parallel(files, changed_lines_map)

        # 保存结果缓存到磁盘
        self._result_cache.save()
        cache_stats = self._result_cache.get_stats()
        self.logger.info(f"Result cache stats: {cache_stats}")

        return violations

    def _check_files_sequential(self, files: List[str], changed_lines_map: Dict[str, Set[int]] = None) -> List[Violation]:
        """串行检查文件"""
        all_violations = []

        for i, file_path in enumerate(files):
            changed_lines = changed_lines_map.get(file_path, set()) if changed_lines_map else None
            violations = self.check_file(file_path, changed_lines)
            all_violations.extend(violations)
            if violations:
                self.logger.debug(f"File {i+1}/{len(files)} ({Path(file_path).name}): {len(violations)} violations")

        self.logger.info(f"Total violations found: {len(all_violations)}")
        return all_violations

    def _check_files_parallel(self, files: List[str], changed_lines_map: Dict[str, Set[int]] = None) -> List[Violation]:
        """并行检查文件"""
        all_violations = []
        violations_lock = Lock()
        completed_count = 0
        total_files = len(files)

        def check_single_file(file_path: str) -> Tuple[str, List[Violation]]:
            """单文件检查任务"""
            changed_lines = changed_lines_map.get(file_path, set()) if changed_lines_map else None
            return file_path, self.check_file(file_path, changed_lines)

        # 确定工作线程数
        workers = self.max_workers
        if workers <= 0:
            import os
            workers = min(32, (os.cpu_count() or 1) * 2)
        workers = min(workers, len(files))

        self.logger.debug(f"Starting parallel check with {workers} workers")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(check_single_file, f): f for f in files}

            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    _, violations = future.result()
                    with violations_lock:
                        all_violations.extend(violations)
                        completed_count += 1
                        if violations:
                            self.logger.debug(f"File {completed_count}/{total_files} ({Path(file_path).name}): {len(violations)} violations")
                except Exception as e:
                    self.logger.error(f"Failed to check {file_path}: {e}")
                    with violations_lock:
                        completed_count += 1

        self.logger.info(f"Total violations found: {len(all_violations)}")

        # 输出缓存统计
        cache_stats = self._file_cache.get_stats()
        self.logger.debug(f"File cache stats: hit_rate={cache_stats['hit_rate']:.1f}%, "
                         f"cached_files={cache_stats['cached_files']}, "
                         f"size={cache_stats['cache_size_mb']:.2f}MB")

        return all_violations
