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
                    PRIMARY KEY (run_id, rule_id)
                )
                """
            )
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
            # 违规详情表（用于去重）
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_key TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    column INTEGER,
                    rule_id TEXT NOT NULL,
                    severity TEXT,
                    message TEXT,
                    code_hash TEXT,
                    source TEXT,
                    pod_name TEXT,
                    related_lines TEXT,
                    context TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    UNIQUE(project_key, file_path, rule_id, code_hash)
                )
                """
            )
            # 尝试添加新字段（兼容旧数据库）
            for col, col_type in [
                ("source", "TEXT"),
                ("pod_name", "TEXT"),
                ("related_lines", "TEXT"),
                ("context", "TEXT"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE violations ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass  # 字段已存在
            # 创建索引加速查询
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_violations_project_key
                ON violations(project_key)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_violations_last_seen
                ON violations(last_seen)
                """
            )

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

        # 处理 violations（去重 upsert）
        if "violations" in payload and isinstance(payload.get("violations"), list):
            self.upsert_violations(project_key, payload.get("violations", []))

        return True, "ok"

    def replace_rule_counts(self, run_id: str, rules: Dict[str, Any]) -> None:
        """替换规则计数"""
        with self._connect() as conn:
            conn.execute("DELETE FROM rule_counts WHERE run_id=?", (run_id,))
            for rule_id, item in rules.items():
                if not isinstance(item, dict):
                    continue
                conn.execute(
                    "INSERT INTO rule_counts (run_id, rule_id, severity, enabled, count) VALUES (?, ?, ?, ?, ?)",
                    (
                        run_id,
                        rule_id,
                        item.get("severity", "warning"),
                        1 if item.get("enabled", True) else 0,
                        int(item.get("count", 0)),
                    )
                )

    def upsert_violations(self, project_key: str, violations: list) -> Tuple[int, int]:
        """
        Upsert 违规记录（基于 code_hash 去重）

        相同 (project_key, file_path, rule_id, code_hash) 的记录只更新 last_seen，
        不同的记录则插入新行。

        支持两种输入格式：
        - List[Violation]: Violation 对象列表（推荐）
        - List[Dict]: 字典列表（兼容旧格式）

        注意：SQLite 的 UNIQUE 约束对 NULL 的处理是 NULL != NULL，
        所以如果 code_hash 为空，需要生成一个基于位置的 fallback hash。

        Args:
            project_key: 项目 key
            violations: 违规列表

        Returns:
            (inserted_count, updated_count)
        """
        import hashlib
        now = datetime.now().isoformat()
        inserted = 0
        updated = 0

        with self._connect() as conn:
            for v in violations:
                # 支持 Violation 对象和字典两种格式
                if hasattr(v, 'to_dict'):
                    # Violation 对象
                    file_path = v.file_path
                    line = v.line
                    column = v.column
                    rule_id = v.rule_id
                    severity = v.severity.value if hasattr(v.severity, 'value') else str(v.severity)
                    message = v.message
                    code_hash = v.code_hash
                    source = v.source
                    pod_name = v.pod_name
                    related_lines = json.dumps(list(v.related_lines)) if v.related_lines else None
                    context = v.context
                elif isinstance(v, dict):
                    # 字典格式（兼容）
                    file_path = v.get("file") or v.get("file_path", "")
                    line = v.get("line", 0)
                    column = v.get("column", 0)
                    rule_id = v.get("rule_id", "")
                    severity = v.get("severity", "warning")
                    message = v.get("message", "")
                    code_hash = v.get("code_hash")
                    source = v.get("source")
                    pod_name = v.get("pod_name")
                    related_lines = json.dumps(v.get("related_lines")) if v.get("related_lines") else None
                    context = v.get("context")
                else:
                    continue

                if not file_path or not rule_id:
                    continue

                # 如果没有 code_hash，生成一个基于位置的 fallback hash
                if not code_hash:
                    fallback_input = f"{file_path}:{line}:{rule_id}"
                    code_hash = hashlib.md5(fallback_input.encode()).hexdigest()[:16]

                # 尝试 upsert
                try:
                    conn.execute(
                        """
                        INSERT INTO violations
                            (project_key, file_path, line, column, rule_id, severity, message, code_hash,
                             source, pod_name, related_lines, context, first_seen, last_seen)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(project_key, file_path, rule_id, code_hash)
                        DO UPDATE SET
                            line = excluded.line,
                            column = excluded.column,
                            severity = excluded.severity,
                            message = excluded.message,
                            source = excluded.source,
                            pod_name = excluded.pod_name,
                            related_lines = excluded.related_lines,
                            context = excluded.context,
                            last_seen = excluded.last_seen
                        """,
                        (project_key, file_path, line, column, rule_id, severity, message, code_hash,
                         source, pod_name, related_lines, context, now, now)
                    )
                    inserted += 1
                except Exception as e:
                    self.logger.debug(f"Failed to upsert violation: {e}")

        return inserted, updated

    def get_violations(
        self,
        project_key: str,
        rule_id: Optional[str] = None,
        file_path: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        获取违规详情

        返回字典格式，可通过 Violation.from_dict() 反序列化为 Violation 对象。
        """
        query = """
            SELECT file_path, line, column, rule_id, severity, message, code_hash,
                   source, pod_name, related_lines, context, first_seen, last_seen
            FROM violations
            WHERE project_key = ?
        """
        params: List[Any] = [project_key]

        if rule_id:
            query += " AND rule_id = ?"
            params.append(rule_id)
        if file_path:
            query += " AND file_path = ?"
            params.append(file_path)

        query += " ORDER BY last_seen DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        results = []
        for row in rows:
            item = {
                "file_path": row[0],
                "line": row[1],
                "column": row[2],
                "rule_id": row[3],
                "severity": row[4],
                "message": row[5],
                "code_hash": row[6],
                "source": row[7],
                "pod_name": row[8],
                "first_seen": row[11],
                "last_seen": row[12],
            }
            # 解析 related_lines JSON
            if row[9]:
                try:
                    item["related_lines"] = json.loads(row[9])
                except json.JSONDecodeError:
                    pass
            # context
            if row[10]:
                item["context"] = row[10]
            results.append(item)

        return results

    def get_violations_stats(self, project_key: str) -> Dict[str, Any]:
        """获取违规统计（去重后的实际违规数）"""
        with self._connect() as conn:
            # 总违规数（去重后）
            total = conn.execute(
                "SELECT COUNT(*) FROM violations WHERE project_key = ?",
                (project_key,)
            ).fetchone()[0]

            # 按规则统计
            by_rule = conn.execute(
                """
                SELECT rule_id, COUNT(*) as count
                FROM violations
                WHERE project_key = ?
                GROUP BY rule_id
                ORDER BY count DESC
                """,
                (project_key,)
            ).fetchall()

            # 按严重级别统计
            by_severity = conn.execute(
                """
                SELECT severity, COUNT(*) as count
                FROM violations
                WHERE project_key = ?
                GROUP BY severity
                """,
                (project_key,)
            ).fetchall()

        return {
            "total": total,
            "by_rule": {row[0]: row[1] for row in by_rule},
            "by_severity": {row[0]: row[1] for row in by_severity},
        }

    def get_current_violations_summary(
        self,
        project_key: Optional[str],
        project_name: Optional[str] = None,
    ) -> Tuple[int, int, int]:
        """
        获取当前违规汇总（去重后的实际违规数）

        从 violations 表获取数据，返回去重后的真实违规计数。
        用于 Dashboard 显示当前项目的实际违规状态。

        Args:
            project_key: 项目 key
            project_name: 项目名称（暂不使用，保留接口一致性）

        Returns:
            (total, warning, error) 三元组
        """
        if not project_key:
            # 无项目筛选时返回全部
            with self._connect() as conn:
                total = conn.execute("SELECT COUNT(*) FROM violations").fetchone()[0]
                warning = conn.execute(
                    "SELECT COUNT(*) FROM violations WHERE severity = 'warning'"
                ).fetchone()[0]
                error = conn.execute(
                    "SELECT COUNT(*) FROM violations WHERE severity = 'error'"
                ).fetchone()[0]
            return (total, warning, error)

        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM violations WHERE project_key = ?",
                (project_key,)
            ).fetchone()[0]
            warning = conn.execute(
                "SELECT COUNT(*) FROM violations WHERE project_key = ? AND severity = 'warning'",
                (project_key,)
            ).fetchone()[0]
            error = conn.execute(
                "SELECT COUNT(*) FROM violations WHERE project_key = ? AND severity = 'error'",
                (project_key,)
            ).fetchone()[0]
        return (total, warning, error)

    def get_current_rule_stats(
        self,
        project_key: Optional[str],
        project_name: Optional[str] = None,
    ) -> List[Tuple[str, str, int, int]]:
        """
        获取当前规则统计（去重后的实际违规数）

        从 violations 表获取数据，返回去重后的真实规则违规计数。

        Args:
            project_key: 项目 key
            project_name: 项目名称（暂不使用）

        Returns:
            List of (rule_id, severity, enabled, count) tuples
        """
        query = """
            SELECT rule_id, severity, 1 as enabled, COUNT(*) as count
            FROM violations
            WHERE 1=1
        """
        params: List[Any] = []
        if project_key:
            query += " AND project_key = ?"
            params.append(project_key)
        query += " GROUP BY rule_id, severity ORDER BY count DESC"

        with self._connect() as conn:
            return conn.execute(query, params).fetchall()

    def cleanup_stale_violations(self, project_key: str, days: int = 30) -> int:
        """清理过期的违规记录（超过 N 天未更新）"""
        if days <= 0:
            return 0
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM violations
                WHERE project_key = ? AND last_seen < date('now', ?)
                """,
                (project_key, f"-{days} days")
            )
            return cursor.rowcount

    # -------------------- 统计查询 --------------------

    def list_projects(self) -> List[Tuple[str, str]]:
        """列出所有项目"""
        with self._connect() as conn:
            return conn.execute(
                "SELECT DISTINCT project_key, project_name FROM runs ORDER BY project_key, project_name"
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
