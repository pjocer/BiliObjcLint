"""
BiliObjCLint Server - 数据库模块
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils import ensure_dir
from .auth import hash_password, verify_password

# 延迟导入避免循环依赖
# from ..lint.reporter import Violation, Severity


class Database:
    """SQLite 数据库封装"""

    def __init__(self, path: Path, logger: logging.Logger):
        """
        初始化数据库

        Args:
            path: 数据库文件路径
            logger: 日志记录器
        """
        self.path = path
        self.logger = logger
        ensure_dir(self.path.parent)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(str(self.path))

    def _init_db(self) -> None:
        """初始化数据库表"""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    project_key TEXT,
                    project_name TEXT,
                    created_at TEXT,
                    tool_name TEXT,
                    tool_version TEXT,
                    total INTEGER,
                    warning INTEGER,
                    error INTEGER,
                    summary_json TEXT,
                    config_snapshot TEXT,
                    autofix_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rule_counts (
                    run_id TEXT,
                    rule_id TEXT,
                    severity TEXT,
                    enabled INTEGER,
                    count INTEGER,
                    order_index INTEGER DEFAULT 0,
                    rule_name TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    PRIMARY KEY (run_id, rule_id)
                )
                """
            )
            # 迁移：为旧表添加新列
            try:
                conn.execute("ALTER TABLE rule_counts ADD COLUMN order_index INTEGER DEFAULT 0")
            except Exception:
                pass  # 列已存在
            try:
                conn.execute("ALTER TABLE rule_counts ADD COLUMN rule_name TEXT DEFAULT ''")
            except Exception:
                pass  # 列已存在
            try:
                conn.execute("ALTER TABLE rule_counts ADD COLUMN description TEXT DEFAULT ''")
            except Exception:
                pass  # 列已存在
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password_hash TEXT,
                    role TEXT,
                    created_at TEXT
                )
                """
            )
            # 项目元数据表（Per-project 表设计）
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_key TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(project_key, project_name)
                )
                """
            )
            # 删除旧的 violations 表（测试阶段，数据不重要）
            conn.execute("DROP TABLE IF EXISTS violations")

    def _get_table_suffix(self, project_key: str, project_name: str) -> str:
        """计算 violations 表后缀

        Args:
            project_key: 项目组标识
            project_name: 项目名称

        Returns:
            8 字符的 MD5 哈希后缀
        """
        import hashlib
        key = f"{project_key}:{project_name}"
        return hashlib.md5(key.encode()).hexdigest()[:8]

    def _get_or_create_violations_table(self, project_key: str, project_name: str) -> str:
        """获取或创建 Per-project violations 表

        Args:
            project_key: 项目组标识
            project_name: 项目名称

        Returns:
            表名（violations_{suffix}）
        """
        with self._connect() as conn:
            # 查询已存在的表名
            row = conn.execute(
                "SELECT table_name FROM projects WHERE project_key = ? AND project_name = ?",
                (project_key, project_name)
            ).fetchone()

            if row:
                return row[0]

            # 创建新表
            suffix = self._get_table_suffix(project_key, project_name)
            table_name = f"violations_{suffix}"

            # 创建 violations 表（使用 violation_id 作为唯一约束）
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    violation_id TEXT NOT NULL UNIQUE,
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    column INTEGER,
                    rule_id TEXT NOT NULL,
                    rule_name TEXT,
                    sub_type TEXT,
                    severity TEXT,
                    message TEXT,
                    code_hash TEXT,
                    source TEXT,
                    pod_name TEXT,
                    related_lines TEXT,
                    context TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                )
                """
            )
            # 创建索引
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{suffix}_rule_id ON {table_name}(rule_id)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{suffix}_last_seen ON {table_name}(last_seen)"
            )

            # 记录到 projects 表
            conn.execute(
                "INSERT INTO projects (project_key, project_name, table_name, created_at) VALUES (?, ?, ?, ?)",
                (project_key, project_name, table_name, datetime.now().isoformat())
            )

            self.logger.info(f"Created violations table: {table_name} for {project_key}/{project_name}")
            return table_name

    def _list_all_violations_tables(self) -> List[Tuple[str, str, str]]:
        """列出所有 violations 表

        Returns:
            List of (project_key, project_name, table_name) tuples
        """
        with self._connect() as conn:
            return conn.execute(
                "SELECT project_key, project_name, table_name FROM projects ORDER BY project_key, project_name"
            ).fetchall()

    # -------------------- 用户管理 --------------------

    def ensure_admin(self, username: str, password: str) -> None:
        """确保管理员账号存在"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username=?",
                (username,)
            ).fetchone()
            if row:
                if password:
                    conn.execute(
                        "UPDATE users SET password_hash=? WHERE username=?",
                        (hash_password(password), username)
                    )
                return
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (username, hash_password(password), "admin", datetime.now().isoformat())
            )

    def verify_user(self, username: str, password: str) -> Optional[str]:
        """
        验证用户凭证

        Returns:
            用户角色，验证失败返回 None
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash, role FROM users WHERE username=?",
                (username,)
            ).fetchone()
            if not row:
                return None
            if verify_password(row[0], password):
                return row[1]
            return None

    def list_users(self) -> List[Tuple[str, str, str]]:
        """列出所有用户"""
        with self._connect() as conn:
            return conn.execute(
                "SELECT username, role, created_at FROM users ORDER BY id ASC"
            ).fetchall()

    def create_user(self, username: str, password: str, role: str) -> Tuple[bool, str]:
        """创建用户"""
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                    (username, hash_password(password), role, datetime.now().isoformat())
                )
            return True, "ok"
        except sqlite3.IntegrityError:
            return False, "用户名已存在"

    def delete_user(self, username: str) -> None:
        """删除用户"""
        with self._connect() as conn:
            conn.execute("DELETE FROM users WHERE username=?", (username,))

    # -------------------- 运行记录 --------------------

    def get_run(self, run_id: str) -> Optional[Tuple]:
        """获取单次运行记录"""
        with self._connect() as conn:
            return conn.execute(
                """SELECT run_id, project_key, project_name, created_at, tool_name, tool_version,
                   total, warning, error, summary_json, config_snapshot, autofix_json
                   FROM runs WHERE run_id=?""",
                (run_id,)
            ).fetchone()

    def upsert_run(self, payload: Dict[str, Any]) -> Tuple[bool, str]:
        """插入或更新运行记录"""
        run_id = payload.get("run_id")
        if not run_id:
            return False, "missing run_id"

        existing = self.get_run(run_id)

        project = payload.get("project", {}) or {}
        tool = payload.get("tool", {}) or {}
        summary = payload.get("summary")
        config_snapshot = payload.get("config_snapshot")
        autofix = payload.get("autofix")

        created_at = payload.get("created_at") or (existing[3] if existing else datetime.now().isoformat())
        project_key = project.get("key") or (existing[1] if existing else "")
        project_name = project.get("name") or (existing[2] if existing else "")
        tool_name = tool.get("name") or (existing[4] if existing else "biliobjclint")
        tool_version = tool.get("version") or (existing[5] if existing else "unknown")

        total = summary.get("total") if isinstance(summary, dict) else (existing[6] if existing else None)
        warning = summary.get("warning") if isinstance(summary, dict) else (existing[7] if existing else None)
        error = summary.get("error") if isinstance(summary, dict) else (existing[8] if existing else None)

        summary_json = json.dumps(summary, ensure_ascii=False) if summary is not None else (existing[9] if existing else None)
        config_json = json.dumps(config_snapshot, ensure_ascii=False) if config_snapshot is not None else (existing[10] if existing else None)
        autofix_json = json.dumps(autofix, ensure_ascii=False) if autofix is not None else (existing[11] if existing else None)

        with self._connect() as conn:
            if existing:
                conn.execute(
                    """
                    UPDATE runs SET project_key=?, project_name=?, created_at=?, tool_name=?, tool_version=?,
                        total=?, warning=?, error=?, summary_json=?, config_snapshot=?, autofix_json=?
                    WHERE run_id=?
                    """,
                    (project_key, project_name, created_at, tool_name, tool_version,
                     total, warning, error, summary_json, config_json, autofix_json, run_id)
                )
            else:
                conn.execute(
                    """
                    INSERT INTO runs (run_id, project_key, project_name, created_at, tool_name, tool_version,
                        total, warning, error, summary_json, config_snapshot, autofix_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, project_key, project_name, created_at, tool_name, tool_version,
                     total, warning, error, summary_json, config_json, autofix_json)
                )

        if "rules" in payload and isinstance(payload.get("rules"), dict):
            self.replace_rule_counts(run_id, payload.get("rules", {}))

        # 处理 violations（去重 upsert 到 Per-project 表）
        if "violations" in payload and isinstance(payload.get("violations"), list):
            if project_key and project_name:
                self.upsert_violations(project_key, project_name, payload.get("violations", []))

        return True, "ok"

    def replace_rule_counts(self, run_id: str, rules: Dict[str, Any]) -> None:
        """替换规则计数（保留配置中的顺序、规则名称和描述）"""
        with self._connect() as conn:
            conn.execute("DELETE FROM rule_counts WHERE run_id=?", (run_id,))
            for order_index, (rule_id, item) in enumerate(rules.items()):
                if not isinstance(item, dict):
                    continue
                conn.execute(
                    "INSERT INTO rule_counts (run_id, rule_id, severity, enabled, count, order_index, rule_name, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        rule_id,
                        item.get("severity", "warning"),
                        1 if item.get("enabled", True) else 0,
                        int(item.get("count", 0)),
                        order_index,
                        item.get("rule_name", ""),
                        item.get("description", ""),
                    )
                )

    def upsert_violations(
        self,
        project_key: str,
        project_name: str,
        violations: list,
    ) -> Tuple[int, int]:
        """
        Upsert 违规记录到 Per-project 表（基于 violation_id 去重）

        相同 violation_id 的记录只更新 last_seen 和其他字段，
        不同的记录则插入新行。

        支持两种输入格式：
        - List[Violation]: Violation 对象列表（推荐）
        - List[Dict]: 字典列表（兼容旧格式）

        Args:
            project_key: 项目组标识
            project_name: 项目名称
            violations: 违规列表

        Returns:
            (inserted_count, updated_count)
        """
        import hashlib
        now = datetime.now().isoformat()
        inserted = 0
        updated = 0

        # 获取或创建 Per-project violations 表
        table_name = self._get_or_create_violations_table(project_key, project_name)

        with self._connect() as conn:
            for v in violations:
                # 支持 Violation 对象和字典两种格式
                if hasattr(v, 'to_dict'):
                    # Violation 对象
                    file_path = v.file_path
                    line = v.line
                    column = v.column
                    rule_id = v.rule_id
                    rule_name = v.rule_name
                    severity = v.severity.value if hasattr(v.severity, 'value') else str(v.severity)
                    message = v.message
                    code_hash = v.code_hash
                    source = v.source
                    pod_name = v.pod_name
                    related_lines = json.dumps(list(v.related_lines)) if v.related_lines else None
                    context = v.context
                    sub_type = v.sub_type
                    violation_id = v.violation_id
                elif isinstance(v, dict):
                    # 字典格式（兼容）
                    file_path = v.get("file") or v.get("file_path", "")
                    line = v.get("line", 0)
                    column = v.get("column", 0)
                    rule_id = v.get("rule_id", "")
                    rule_name = v.get("rule_name")
                    severity = v.get("severity", "warning")
                    message = v.get("message", "")
                    code_hash = v.get("code_hash")
                    source = v.get("source")
                    pod_name = v.get("pod_name")
                    related_lines = json.dumps(v.get("related_lines")) if v.get("related_lines") else None
                    context = v.get("context")
                    sub_type = v.get("sub_type")
                    violation_id = v.get("violation_id")
                else:
                    continue

                if not file_path or not rule_id:
                    continue

                # 如果没有 violation_id，生成一个基于位置的 fallback id
                if not violation_id:
                    fallback_input = f"{file_path}:{line}:{rule_id}:{sub_type or ''}:{code_hash or ''}"
                    violation_id = hashlib.md5(fallback_input.encode()).hexdigest()[:16]

                # 检查是否已存在（区分 insert vs update）
                try:
                    exists = conn.execute(
                        f"SELECT 1 FROM {table_name} WHERE violation_id = ?",
                        (violation_id,)
                    ).fetchone() is not None

                    if exists:
                        # 更新已存在的记录
                        conn.execute(
                            f"""
                            UPDATE {table_name} SET
                                line = ?,
                                column = ?,
                                rule_name = ?,
                                severity = ?,
                                message = ?,
                                source = ?,
                                pod_name = ?,
                                related_lines = ?,
                                context = ?,
                                last_seen = ?
                            WHERE violation_id = ?
                            """,
                            (line, column, rule_name, severity, message, source, pod_name,
                             related_lines, context, now, violation_id)
                        )
                        updated += 1
                    else:
                        # 插入新记录
                        conn.execute(
                            f"""
                            INSERT INTO {table_name}
                                (violation_id, file_path, line, column, rule_id, rule_name, sub_type, severity, message,
                                 code_hash, source, pod_name, related_lines, context, first_seen, last_seen)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (violation_id, file_path, line, column, rule_id, rule_name, sub_type, severity, message,
                             code_hash, source, pod_name, related_lines, context, now, now)
                        )
                        inserted += 1
                except Exception as e:
                    self.logger.debug(f"Failed to upsert violation: {e}")

        return inserted, updated

    def get_violations(
        self,
        project_key: str,
        project_name: str,
        rule_id: Optional[str] = None,
        sub_type: Optional[str] = None,
        file_path: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        获取违规详情（从 Per-project 表）

        返回字典格式，可通过 Violation.from_dict() 反序列化为 Violation 对象。

        Args:
            project_key: 项目组标识
            project_name: 项目名称
            rule_id: 规则 ID 过滤
            sub_type: 子类型过滤
            file_path: 文件路径过滤
            search: 搜索关键词（匹配 file_path 或 message）
            limit: 返回数量限制
            offset: 分页偏移量

        Returns:
            (violations_list, total_count) 元组
        """
        # 获取表名（不创建新表）
        with self._connect() as conn:
            row = conn.execute(
                "SELECT table_name FROM projects WHERE project_key = ? AND project_name = ?",
                (project_key, project_name)
            ).fetchone()

        if not row:
            return [], 0

        table_name = row[0]

        # 构建查询条件
        where_clauses = ["1=1"]
        params: List[Any] = []

        if rule_id:
            where_clauses.append("rule_id = ?")
            params.append(rule_id)
        if sub_type:
            where_clauses.append("sub_type = ?")
            params.append(sub_type)
        if file_path:
            where_clauses.append("file_path = ?")
            params.append(file_path)
        if search:
            where_clauses.append("(file_path LIKE ? OR message LIKE ?)")
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])

        where_sql = " AND ".join(where_clauses)

        with self._connect() as conn:
            # 获取总数
            count_query = f"SELECT COUNT(*) FROM {table_name} WHERE {where_sql}"
            total = conn.execute(count_query, params).fetchone()[0]

            # 获取分页数据
            query = f"""
                SELECT violation_id, file_path, line, column, rule_id, rule_name, sub_type, severity, message,
                       code_hash, source, pod_name, related_lines, context, first_seen, last_seen
                FROM {table_name}
                WHERE {where_sql}
                ORDER BY last_seen DESC
                LIMIT ? OFFSET ?
            """
            rows = conn.execute(query, params + [limit, offset]).fetchall()

        results = []
        for row in rows:
            item = {
                "violation_id": row[0],
                "file_path": row[1],
                "line": row[2],
                "column": row[3],
                "rule_id": row[4],
                "rule_name": row[5],
                "sub_type": row[6],
                "severity": row[7],
                "message": row[8],
                "code_hash": row[9],
                "source": row[10],
                "pod_name": row[11],
                "first_seen": row[14],
                "last_seen": row[15],
            }
            # 解析 related_lines JSON
            if row[12]:
                try:
                    item["related_lines"] = json.loads(row[12])
                except json.JSONDecodeError:
                    pass
            # context
            if row[13]:
                item["context"] = row[13]
            results.append(item)

        return results, total

    def get_violation_by_id(
        self,
        project_key: str,
        project_name: str,
        violation_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        根据 violation_id 获取单个违规详情

        Args:
            project_key: 项目组标识
            project_name: 项目名称
            violation_id: 违规 ID

        Returns:
            违规详情字典，不存在返回 None
        """
        # 获取表名
        with self._connect() as conn:
            row = conn.execute(
                "SELECT table_name FROM projects WHERE project_key = ? AND project_name = ?",
                (project_key, project_name)
            ).fetchone()

        if not row:
            return None

        table_name = row[0]

        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT violation_id, file_path, line, column, rule_id, rule_name, sub_type, severity, message,
                       code_hash, source, pod_name, related_lines, context, first_seen, last_seen
                FROM {table_name}
                WHERE violation_id = ?
                """,
                (violation_id,)
            ).fetchone()

        if not row:
            return None

        item = {
            "violation_id": row[0],
            "file_path": row[1],
            "line": row[2],
            "column": row[3],
            "rule_id": row[4],
            "rule_name": row[5],
            "sub_type": row[6],
            "severity": row[7],
            "message": row[8],
            "code_hash": row[9],
            "source": row[10],
            "pod_name": row[11],
            "first_seen": row[14],
            "last_seen": row[15],
        }
        # 解析 related_lines JSON
        if row[12]:
            try:
                item["related_lines"] = json.loads(row[12])
            except json.JSONDecodeError:
                pass
        # context
        if row[13]:
            item["context"] = row[13]

        return item

    def get_violations_stats(
        self,
        project_key: str,
        project_name: str,
    ) -> Dict[str, Any]:
        """获取违规统计（去重后的实际违规数）

        Args:
            project_key: 项目组标识
            project_name: 项目名称

        Returns:
            统计信息字典
        """
        # 获取表名
        with self._connect() as conn:
            row = conn.execute(
                "SELECT table_name FROM projects WHERE project_key = ? AND project_name = ?",
                (project_key, project_name)
            ).fetchone()

        if not row:
            return {"total": 0, "by_rule": {}, "by_severity": {}}

        table_name = row[0]

        with self._connect() as conn:
            # 总违规数（去重后）
            total = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

            # 按规则统计
            by_rule = conn.execute(
                f"""
                SELECT rule_id, COUNT(*) as count
                FROM {table_name}
                GROUP BY rule_id
                ORDER BY count DESC
                """
            ).fetchall()

            # 按严重级别统计
            by_severity = conn.execute(
                f"""
                SELECT severity, COUNT(*) as count
                FROM {table_name}
                GROUP BY severity
                """
            ).fetchall()

        return {
            "total": total,
            "by_rule": {row[0]: row[1] for row in by_rule},
            "by_severity": {row[0]: row[1] for row in by_severity},
        }

    def get_available_filters(
        self,
        project_key: str,
        project_name: str,
    ) -> Tuple[List[Tuple[str, Optional[str], int]], List[str]]:
        """获取可用的筛选选项

        Args:
            project_key: 项目组标识
            project_name: 项目名称

        Returns:
            (rules, sub_types) 元组:
            - rules: List of (rule_id, rule_name, count)
            - sub_types: List of sub_type values
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT table_name FROM projects WHERE project_key = ? AND project_name = ?",
                (project_key, project_name)
            ).fetchone()

        if not row:
            return [], []

        table_name = row[0]

        with self._connect() as conn:
            # 获取规则列表（包含 rule_name 和 count）
            rules_rows = conn.execute(
                f"""
                SELECT rule_id, rule_name, COUNT(*) as count
                FROM {table_name}
                GROUP BY rule_id
                ORDER BY count DESC
                """
            ).fetchall()

            # 获取子类型列表
            sub_types_rows = conn.execute(
                f"""
                SELECT DISTINCT sub_type
                FROM {table_name}
                WHERE sub_type IS NOT NULL AND sub_type != ''
                ORDER BY sub_type
                """
            ).fetchall()

        rules = [(row[0], row[1], row[2]) for row in rules_rows]
        sub_types = [row[0] for row in sub_types_rows]

        return rules, sub_types

    def get_current_violations_summary(
        self,
        project_key: Optional[str],
        project_name: Optional[str] = None,
    ) -> Tuple[int, int, int]:
        """
        获取当前违规汇总（去重后的实际违规数）

        从 Per-project violations 表获取数据，返回去重后的真实违规计数。
        用于 Dashboard 显示当前项目的实际违规状态。

        Args:
            project_key: 项目组标识
            project_name: 项目名称

        Returns:
            (total, warning, error) 三元组
        """
        if not project_key or not project_name:
            # 无项目筛选时聚合所有 violations 表
            total, warning, error = 0, 0, 0
            tables = self._list_all_violations_tables()
            with self._connect() as conn:
                for _, _, table_name in tables:
                    try:
                        total += conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                        warning += conn.execute(
                            f"SELECT COUNT(*) FROM {table_name} WHERE severity = 'warning'"
                        ).fetchone()[0]
                        error += conn.execute(
                            f"SELECT COUNT(*) FROM {table_name} WHERE severity = 'error'"
                        ).fetchone()[0]
                    except Exception:
                        continue
            return (total, warning, error)

        # 获取特定项目的表名
        with self._connect() as conn:
            row = conn.execute(
                "SELECT table_name FROM projects WHERE project_key = ? AND project_name = ?",
                (project_key, project_name)
            ).fetchone()

        if not row:
            return (0, 0, 0)

        table_name = row[0]

        with self._connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            warning = conn.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE severity = 'warning'"
            ).fetchone()[0]
            error = conn.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE severity = 'error'"
            ).fetchone()[0]
        return (total, warning, error)

    def _get_latest_rule_configs(self, project_key: str) -> Dict[str, Dict[str, Any]]:
        """获取指定 project_key 最近一次 run 的规则配置

        一个 project_key 下所有 project_name 共享同一套 .biliobjclint.yaml 配置，
        所以从该 project_key 最近一次 run 的 rule_counts 中获取规则的 enabled 状态、顺序、名称和描述。

        Args:
            project_key: 项目组标识

        Returns:
            Dict[rule_id, {"enabled": bool, "severity": str, "order": int, "rule_name": str, "description": str}]
        """
        with self._connect() as conn:
            # 获取该 project_key 最近一次 run
            latest_run = conn.execute(
                """
                SELECT run_id FROM runs
                WHERE project_key = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (project_key,)
            ).fetchone()

            if not latest_run:
                return {}

            run_id = latest_run[0]

            # 获取该 run 的规则配置（按 order_index 排序）
            rows = conn.execute(
                """
                SELECT rule_id, severity, enabled, COALESCE(order_index, 0) as order_index,
                       COALESCE(rule_name, '') as rule_name, COALESCE(description, '') as description
                FROM rule_counts
                WHERE run_id = ?
                ORDER BY order_index
                """,
                (run_id,)
            ).fetchall()

            return {
                row[0]: {"severity": row[1], "enabled": bool(row[2]), "order": row[3], "rule_name": row[4], "description": row[5]}
                for row in rows
            }

    def get_current_rule_stats(
        self,
        project_key: Optional[str],
        project_name: Optional[str] = None,
    ) -> List[Tuple[str, str, str, int, int, str]]:
        """
        获取当前规则统计（去重后的实际违规数）

        从 Per-project violations 表获取违规计数，结合 rule_counts 表获取规则的 enabled 状态。

        Args:
            project_key: 项目组标识
            project_name: 项目名称

        Returns:
            List of (rule_id, rule_name, severity, enabled, count, description) tuples
        """
        if not project_key or not project_name:
            # 聚合所有表的规则统计
            # key: (rule_id, severity), value: (count, rule_name)
            rule_stats: Dict[Tuple[str, str], Tuple[int, str]] = {}
            tables = self._list_all_violations_tables()
            with self._connect() as conn:
                for _, _, table_name in tables:
                    try:
                        rows = conn.execute(
                            f"""
                            SELECT rule_id, MAX(rule_name), severity, COUNT(*) as count
                            FROM {table_name}
                            GROUP BY rule_id, severity
                            """
                        ).fetchall()
                        for rule_id, rule_name, severity, count in rows:
                            key = (rule_id, severity)
                            existing = rule_stats.get(key, (0, None))
                            rule_stats[key] = (existing[0] + count, rule_name or existing[1])
                    except Exception:
                        continue
            # 转换为返回格式并排序（全局视图不显示 enabled 状态，默认为 1，无 description）
            result = [(k[0], v[1] or "", k[1], 1, v[0], "") for k, v in rule_stats.items()]
            return sorted(result, key=lambda x: x[4], reverse=True)

        # 获取特定项目的表名
        with self._connect() as conn:
            row = conn.execute(
                "SELECT table_name FROM projects WHERE project_key = ? AND project_name = ?",
                (project_key, project_name)
            ).fetchone()

        if not row:
            return []

        table_name = row[0]

        # 获取该 project_key 的最新规则配置
        rule_configs = self._get_latest_rule_configs(project_key)

        # 获取违规计数
        with self._connect() as conn:
            violation_rows = conn.execute(
                f"""
                SELECT rule_id, MAX(rule_name) as rule_name, severity, COUNT(*) as count
                FROM {table_name}
                GROUP BY rule_id, severity
                ORDER BY count DESC
                """
            ).fetchall()

        # 合并违规计数和配置的 enabled 状态
        # key: rule_id, value: (rule_name, severity, enabled, count, order, description)
        result_map: Dict[str, Tuple[str, str, int, int, int, str]] = {}

        # 1. 添加有违规的规则
        for rule_id, rule_name, severity, count in violation_rows:
            cfg = rule_configs.get(rule_id, {})
            enabled = 1 if cfg.get("enabled", True) else 0
            order = cfg.get("order", 9999)  # 配置中不存在的规则排在最后
            # 优先使用配置中的 rule_name（来自 rule_counts 表），其次使用 violations 表中的
            display_name = cfg.get("rule_name") or rule_name or ""
            description = cfg.get("description", "")
            result_map[rule_id] = (display_name, severity, enabled, count, order, description)

        # 2. 添加配置中存在但没有违规的规则（主要是 enabled=0 的规则）
        for rule_id, cfg in rule_configs.items():
            if rule_id not in result_map:
                result_map[rule_id] = (cfg.get("rule_name", ""), cfg.get("severity", "warning"), 1 if cfg.get("enabled", True) else 0, 0, cfg.get("order", 9999), cfg.get("description", ""))

        # 转换为返回格式并按配置顺序排序
        result = [(rule_id, data[0], data[1], data[2], data[3], data[5]) for rule_id, data in result_map.items()]
        return sorted(result, key=lambda x: result_map[x[0]][4])

    def cleanup_stale_violations(
        self,
        project_key: str,
        project_name: str,
        days: int = 30,
    ) -> int:
        """清理过期的违规记录（超过 N 天未更新）

        Args:
            project_key: 项目组标识
            project_name: 项目名称
            days: 过期天数

        Returns:
            删除的记录数
        """
        if days <= 0:
            return 0

        # 获取表名
        with self._connect() as conn:
            row = conn.execute(
                "SELECT table_name FROM projects WHERE project_key = ? AND project_name = ?",
                (project_key, project_name)
            ).fetchone()

        if not row:
            return 0

        table_name = row[0]

        with self._connect() as conn:
            cursor = conn.execute(
                f"DELETE FROM {table_name} WHERE last_seen < date('now', ?)",
                (f"-{days} days",)
            )
            return cursor.rowcount

    def cleanup_project(self, project_key: str, project_name: str) -> bool:
        """删除整个项目的 violations 表

        Args:
            project_key: 项目组标识
            project_name: 项目名称

        Returns:
            是否成功删除
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT table_name FROM projects WHERE project_key = ? AND project_name = ?",
                (project_key, project_name)
            ).fetchone()

        if not row:
            return False

        table_name = row[0]

        with self._connect() as conn:
            # 删除表
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            # 删除 projects 记录
            conn.execute(
                "DELETE FROM projects WHERE project_key = ? AND project_name = ?",
                (project_key, project_name)
            )

        self.logger.info(f"Deleted project: {project_key}/{project_name} (table: {table_name})")
        return True

    def get_new_violation_types_today(
        self,
        project_key: str,
        project_name: str,
    ) -> List[Tuple[str, Optional[str], Optional[str], int, Optional[str]]]:
        """获取今日新增的 Violation Type（rule_id + sub_type 组合）

        对比今天和昨天的 violations，返回今天新出现的 (rule_id, sub_type) 组合。

        Args:
            project_key: 项目组标识
            project_name: 项目名称

        Returns:
            List of (rule_id, rule_name, sub_type, count, description) tuples
        """
        # 获取表名
        with self._connect() as conn:
            row = conn.execute(
                "SELECT table_name FROM projects WHERE project_key = ? AND project_name = ?",
                (project_key, project_name)
            ).fetchone()

        if not row:
            return []

        table_name = row[0]

        # 获取 violation types
        with self._connect() as conn:
            # 获取今天首次出现的 violation types
            # 即 first_seen 为今天的 (rule_id, sub_type) 组合
            violation_rows = conn.execute(
                f"""
                SELECT rule_id, MAX(rule_name) as rule_name, sub_type, COUNT(*) as count
                FROM {table_name}
                WHERE date(first_seen) = date('now')
                GROUP BY rule_id, sub_type
                ORDER BY count DESC
                """
            ).fetchall()

        if not violation_rows:
            return []

        # 获取最新的 rule configs（包含 description）
        rule_configs = self._get_latest_rule_configs(project_key)

        # 合并 description
        result = []
        for row in violation_rows:
            rule_id, rule_name, sub_type, count = row
            description = rule_configs.get(rule_id, {}).get("description", "")
            result.append((rule_id, rule_name, sub_type, count, description))

        return result

    # -------------------- 统计查询 --------------------

    def list_project_keys(self) -> List[str]:
        """列出所有 project_key（去重）"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT project_key FROM projects ORDER BY project_key"
            ).fetchall()
        return [row[0] for row in rows]

    def list_project_names(self, project_key: str) -> List[str]:
        """列出指定 project_key 下的所有 project_name

        用于 Dashboard 的级联选择。

        Args:
            project_key: 项目组标识

        Returns:
            project_name 列表
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT project_name FROM projects WHERE project_key = ? ORDER BY project_name",
                (project_key,)
            ).fetchall()
        return [row[0] for row in rows]

    def list_projects(self) -> List[Tuple[str, str]]:
        """列出所有项目（兼容旧接口，从 projects 表获取）"""
        with self._connect() as conn:
            return conn.execute(
                "SELECT DISTINCT project_key, project_name FROM projects ORDER BY project_key, project_name"
            ).fetchall()

    def get_daily_stats(
        self,
        project_key: Optional[str],
        project_name: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        days: Optional[int] = None,
    ) -> List[Tuple[str, int, int, int]]:
        """获取每日统计"""
        query = """
            SELECT substr(created_at, 1, 10) as day,
                   sum(total) as total,
                   sum(warning) as warning,
                   sum(error) as error
            FROM runs
            WHERE 1=1
        """
        params: List[Any] = []
        if project_key:
            query += " AND project_key = ?"
            params.append(project_key)
        if project_name:
            query += " AND project_name = ?"
            params.append(project_name)
        if start_date:
            query += " AND date(created_at) >= date(?)"
            params.append(start_date)
        if end_date:
            query += " AND date(created_at) <= date(?)"
            params.append(end_date)
        if not start_date and not end_date and days is not None and days > 0:
            query += " AND date(created_at) >= date('now', ?)"
            params.append(f"-{days} days")
        query += " GROUP BY day ORDER BY day DESC"
        with self._connect() as conn:
            return conn.execute(query, params).fetchall()

    def get_chart_stats(
        self,
        project_key: Optional[str],
        project_name: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        granularity: str = "day",
    ) -> List[Tuple[str, int, int, int]]:
        """获取趋势图统计数据（支持动态粒度）

        Args:
            project_key: 项目 key
            project_name: 项目名称
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            granularity: 粒度，"hour" 或 "day"

        Returns:
            List of (time_slot, total, warning, error) tuples
        """
        # 根据粒度选择时间截取长度
        # hour: substr(created_at, 1, 13) -> "2026-02-04T10"
        # day: substr(created_at, 1, 10) -> "2026-02-04"
        if granularity == "hour":
            time_expr = "substr(created_at, 1, 13)"
        else:
            time_expr = "substr(created_at, 1, 10)"

        query = f"""
            SELECT {time_expr} as time_slot,
                   sum(total) as total,
                   sum(warning) as warning,
                   sum(error) as error
            FROM runs
            WHERE 1=1
        """
        params: List[Any] = []
        if project_key:
            query += " AND project_key = ?"
            params.append(project_key)
        if project_name:
            query += " AND project_name = ?"
            params.append(project_name)
        if start_date:
            query += " AND date(created_at) >= date(?)"
            params.append(start_date)
        if end_date:
            query += " AND date(created_at) <= date(?)"
            params.append(end_date)
        if not start_date and not end_date:
            # 默认最近 7 天
            query += " AND date(created_at) >= date('now', '-7 days')"
        query += " GROUP BY time_slot ORDER BY time_slot ASC"
        with self._connect() as conn:
            return conn.execute(query, params).fetchall()

    def get_rule_stats(
        self,
        project_key: Optional[str],
        project_name: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        days: Optional[int] = None,
    ) -> List[Tuple[str, str, int, int]]:
        """获取规则统计"""
        query = """
            SELECT rc.rule_id, rc.severity, rc.enabled, sum(rc.count) as total
            FROM rule_counts rc
            JOIN runs r ON r.run_id = rc.run_id
            WHERE 1=1
        """
        params: List[Any] = []
        if project_key:
            query += " AND r.project_key = ?"
            params.append(project_key)
        if project_name:
            query += " AND r.project_name = ?"
            params.append(project_name)
        if start_date:
            query += " AND date(r.created_at) >= date(?)"
            params.append(start_date)
        if end_date:
            query += " AND date(r.created_at) <= date(?)"
            params.append(end_date)
        if not start_date and not end_date and days is not None and days > 0:
            query += " AND date(r.created_at) >= date('now', ?)"
            params.append(f"-{days} days")
        query += " GROUP BY rc.rule_id, rc.severity, rc.enabled ORDER BY total DESC"
        with self._connect() as conn:
            return conn.execute(query, params).fetchall()

    def get_autofix_summary(
        self,
        project_key: Optional[str],
        project_name: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        days: Optional[int] = None,
    ) -> Dict[str, int]:
        """获取 autofix 汇总统计"""
        query = "SELECT autofix_json FROM runs WHERE 1=1"
        params: List[Any] = []
        if project_key:
            query += " AND project_key = ?"
            params.append(project_key)
        if project_name:
            query += " AND project_name = ?"
            params.append(project_name)
        if start_date:
            query += " AND date(created_at) >= date(?)"
            params.append(start_date)
        if end_date:
            query += " AND date(created_at) <= date(?)"
            params.append(end_date)
        if not start_date and not end_date and days is not None and days > 0:
            query += " AND date(created_at) >= date('now', ?)"
            params.append(f"-{days} days")
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        summary = {
            "attempts": 0,
            "success": 0,
            "failed": 0,
            "cancelled": 0,
            "target_total": 0,
        }
        for row in rows:
            if not row or not row[0]:
                continue
            try:
                data = json.loads(row[0])
                s = data.get("summary", {})
                for key in summary:
                    summary[key] += int(s.get(key, 0))
            except Exception:
                continue
        return summary

    def cleanup_retention(self, retention_days: int) -> None:
        """清理过期数据"""
        if retention_days <= 0:
            return
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM rule_counts WHERE run_id IN (SELECT run_id FROM runs WHERE created_at < date('now', ?))",
                (f"-{retention_days} days",)
            )
            conn.execute(
                "DELETE FROM runs WHERE created_at < date('now', ?)",
                (f"-{retention_days} days",)
            )
