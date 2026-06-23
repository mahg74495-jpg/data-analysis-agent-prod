#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLDataSource — any SQLAlchemy-supported DB + DuckDB analysis cache."""
import logging
from typing import List, Optional, Tuple

import duckdb
import pandas as pd

from ._utils import _new_conn, _preview_table_dict, _query, _register, _table_schema_str
from .base import DataSource

log = logging.getLogger(__name__)


class SQLDataSource(DataSource):
    """Connect to any SQLAlchemy-supported database."""

    def __init__(self, connection_string: str, display_name: str = ""):
        from sqlalchemy import create_engine, text, inspect as sa_inspect

        # ClickHouse uses HTTP — pool_pre_ping and traditional connection
        # pooling are incompatible (stateless protocol).
        # Accepts both 'clickhouse://' (older) and 'clickhousedb://' (clickhouse-connect).
        self._is_clickhouse = (
            "clickhouse" in connection_string.lower()
            or "clickhousedb" in connection_string.lower()
        )
        engine_kwargs = {}
        if not self._is_clickhouse:
            engine_kwargs["pool_pre_ping"] = True
            # 回收空闲超过 1 小时的连接，防止数据库服务器主动断开
            engine_kwargs["pool_recycle"] = 3600
        self._engine = create_engine(connection_string, **engine_kwargs)
        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        if display_name:
            self.name = display_name
        else:
            try:
                url = self._engine.url
                self.name = f"{url.host}/{url.database or ''}"
            except Exception:
                self.name = "SQL Database"

        self._inspect = sa_inspect(self._engine)
        # DuckDB cache for materialised analysis tables
        self._cache_conn: Optional[duckdb.DuckDBPyConnection] = None
        self._cache_tables: set = set()

    def is_connected(self) -> bool:
        """Check if the SQL connection is still alive by executing a simple query."""
        try:
            from sqlalchemy import text
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def get_schema(self, tables: Optional[List[str]] = None, summary_only: bool = False) -> str:
        parts: List[str] = []
        # ── 指定表名模式：只返回这几张表的完整 schema ────────────────
        if tables:
            for table in tables:
                try:
                    if self._is_clickhouse:
                        from sqlalchemy import text as sa_text
                        with self._engine.connect() as conn:
                            col_rows = conn.execute(
                                sa_text("SELECT name, type FROM system.columns WHERE table = :t"),
                                {"t": table}
                            ).fetchall()
                        col_lines = [f"  {r[0]}  {r[1]}" for r in col_rows]
                    else:
                        cols = self._inspect.get_columns(table)
                        col_lines = [f"  {c['name']}  {c['type']}" for c in cols]
                    parts.append(f"Table: {table}\n" + "\n".join(col_lines))
                except Exception:
                    parts.append(f"Table: {table}  (schema unavailable)")
            for t in sorted(self._cache_tables):
                if self._cache_conn is None:
                    continue
                rows = self._cache_conn.execute(
                    f'SELECT COUNT(*) FROM "{t}"'
                ).fetchone()[0]
                parts.append(_table_schema_str(self._cache_conn, t, rows))
            return "\n\n".join(parts) if parts else "No tables found."

        # ── summary_only 模式：只返回表名列表 ────────────────────────
        if summary_only:
            try:
                raw_tables = self._inspect.get_table_names()
                if self._is_clickhouse:
                    tables = [t for t in raw_tables
                              if not t.startswith("system.")
                              and not t.startswith(".inner")
                              and "." not in t]
                else:
                    tables = raw_tables
                lines = ["## 数据表列表（摘要）\n"]
                for t in tables[:50]:
                    lines.append(f"- {t}")
                for t in sorted(self._cache_tables):
                    lines.append(f"- {t} (分析表)")
                return "\n".join(lines) if lines else "No tables found."
            except Exception:
                return "No tables found."

        # ── 默认模式：返回所有表的完整 schema ────────────────────────
        try:
            raw_tables = self._inspect.get_table_names()
            if self._is_clickhouse:
                tables = [t for t in raw_tables
                          if not t.startswith("system.")
                          and not t.startswith(".inner")
                          and "." not in t]
            else:
                tables = raw_tables
            tables = tables[:50]
        except Exception:
            tables = []
        for table in tables:
            try:
                if self._is_clickhouse:
                    from sqlalchemy import text as sa_text
                    with self._engine.connect() as conn:
                        col_rows = conn.execute(
                            sa_text("SELECT name, type FROM system.columns WHERE table = :t"),
                            {"t": table}
                        ).fetchall()
                    col_lines = [f"  {r[0]}  {r[1]}" for r in col_rows]
                else:
                    cols = self._inspect.get_columns(table)
                    col_lines = [f"  {c['name']}  {c['type']}" for c in cols]
                parts.append(f"Table: {table}\n" + "\n".join(col_lines))
            except Exception:
                parts.append(f"Table: {table}  (schema unavailable)")
        for t in sorted(self._cache_tables):
            if self._cache_conn is None:
                continue
            rows = self._cache_conn.execute(
                f'SELECT COUNT(*) FROM "{t}"'
            ).fetchone()[0]
            parts.append(_table_schema_str(self._cache_conn, t, rows))
        return "\n\n".join(parts) if parts else "No tables found."

    def execute_query(self, sql: str) -> Tuple[pd.DataFrame, str]:
        if self._cache_conn and any(t in sql for t in self._cache_tables):
            return _query(self._cache_conn, sql)
        from sqlalchemy import text
        try:
            with self._engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            return df, ""
        except Exception as exc:
            return pd.DataFrame(), str(exc)

    def create_analysis_table(self, sql: str, table_name: str = "analysis_data", _df=None) -> str:
        if self._cache_conn is None:
            self._cache_conn = _new_conn()
        if _df is not None:
            _register(self._cache_conn, table_name, _df)
            rows = len(_df)
        else:
            df, err = self.execute_query(sql)
            if err:
                return f"Error building analysis table: {err}"
            _register(self._cache_conn, table_name, df)
            rows = len(df)
        self._cache_tables.add(table_name)
        return _table_schema_str(self._cache_conn, table_name, rows)

    def list_tables(self) -> List[str]:
        # Source DB tables + runtime analysis cache tables.
        try:
            tables = list(self._inspect.get_table_names())
        except Exception:
            tables = []
        for t in sorted(self._cache_tables):
            if t not in tables:
                tables.append(t)
        return tables

    def get_preview(self) -> List[dict]:
        result = []
        # Analysis cache tables
        if self._cache_conn:
            for t in sorted(self._cache_tables):
                try:
                    cols = [r[0] for r in self._cache_conn.execute(f'DESCRIBE "{t}"').fetchall()]
                    total = self._cache_conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                    result.append({"name": f"[分析表] {t}", "columns": cols, "total_rows": total})
                except Exception:
                    continue
        # Source DB tables — just names + columns, no row data
        try:
            raw_tables = self._inspect.get_table_names()
            # ClickHouse: filter out system/internal tables
            if self._is_clickhouse:
                tables = [t for t in raw_tables
                          if not t.startswith("system.")
                          and not t.startswith(".inner")
                          and "." not in t]
            else:
                tables = raw_tables
            tables = tables[:20]
        except Exception:
            tables = []
        for t in tables:
            try:
                from sqlalchemy import text as _text
                with self._engine.connect() as _c:
                    col_rows = _c.execute(_text(f"SELECT * FROM `{t}` LIMIT 0")).keys()
                    cols = list(col_rows)
                result.append({"name": t, "columns": cols, "total_rows": None})
            except Exception:
                result.append({"name": t, "columns": [], "total_rows": None})
        return result

    def get_preview_table(self, table_name: str, max_rows: int = 100) -> dict:
        # Check analysis cache first (DuckDB-backed)
        if self._cache_conn and table_name.startswith("[分析表] "):
            real = table_name[len("[分析表] "):]
            return _preview_table_dict(self._cache_conn, real, table_name, max_rows)
        # Source DB table — goes through SQLAlchemy
        df, err = self.execute_query(f"SELECT * FROM `{table_name}` LIMIT {max_rows}")
        if err:
            return {"name": table_name, "columns": [], "rows": [], "total_rows": None, "error": err}
        rows = [["" if v is None else str(v) for v in row] for row in df.itertuples(index=False)]
        return {"name": table_name, "columns": list(df.columns),
                "rows": rows, "total_rows": None}
