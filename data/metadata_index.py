# -*- coding: utf-8 -*-
"""
元数据索引 — 平板显示制造行业表级元数据存储与检索。

用于「两阶段路由」：
  Phase 1: Agent 调用 search_relevant_tables(keywords) 检索最相关的 3-5 张表
  Phase 2: Agent 仅对这几张表调用 get_schema

存储位置: uploads/knowledge/table_metadata.db (SQLite + FTS5)
"""
import sqlite3
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_DB_DIR = _PROJECT_ROOT / "uploads" / "knowledge"
_DB_PATH = _DB_DIR / "table_metadata.db"


def _ensure_dir() -> None:
    _DB_DIR.mkdir(parents=True, exist_ok=True)


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS table_metadata (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name    TEXT NOT NULL UNIQUE,
            business_name TEXT DEFAULT '',
            process_stage TEXT DEFAULT '',       -- Array / Cell / Module / Common
            description   TEXT DEFAULT '',
            key_columns   TEXT DEFAULT '',        -- 逗号分隔
            estimated_rows INTEGER DEFAULT 0,
            tags          TEXT DEFAULT '',        -- 逗号分隔的业务标签
            view_name     TEXT DEFAULT '',        -- 对应的宽表/视图名
            partition_key TEXT DEFAULT '',        -- 分区键（如 month/lot_id）
            sample_sql    TEXT DEFAULT '',        -- 典型查询 SQL
            is_active     INTEGER DEFAULT 1,
            updated_at    REAL NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS table_metadata_fts
            USING fts5(
                table_name, business_name, description, tags, key_columns,
                content=table_metadata, content_rowid=id
            );

        CREATE INDEX IF NOT EXISTS idx_meta_stage ON table_metadata(process_stage);
        CREATE INDEX IF NOT EXISTS idx_meta_active ON table_metadata(is_active);
    """)
    conn.commit()


class MetadataIndex:
    """Thread-safe 表级元数据索引，支持 FTS5 全文检索。"""

    def __init__(self, db_path: Optional[Path] = None):
        _ensure_dir()
        self._path = db_path or _DB_PATH
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        _init_db(self._conn)

    def _now(self) -> float:
        return time.time()

    def _rows(self, cur) -> List[dict]:
        return [dict(r) for r in cur.fetchall()]

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def upsert(self, record: dict) -> bool:
        """插入或更新一条表元数据。"""
        try:
            self._conn.execute(
                """INSERT INTO table_metadata
                   (table_name, business_name, process_stage, description,
                    key_columns, estimated_rows, tags, view_name,
                    partition_key, sample_sql, is_active, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(table_name) DO UPDATE SET
                       business_name=excluded.business_name,
                       process_stage=excluded.process_stage,
                       description=excluded.description,
                       key_columns=excluded.key_columns,
                       estimated_rows=excluded.estimated_rows,
                       tags=excluded.tags,
                       view_name=excluded.view_name,
                       partition_key=excluded.partition_key,
                       sample_sql=excluded.sample_sql,
                       is_active=excluded.is_active,
                       updated_at=excluded.updated_at""",
                (
                    record.get("table_name", ""),
                    record.get("business_name", ""),
                    record.get("process_stage", ""),
                    record.get("description", ""),
                    record.get("key_columns", ""),
                    int(record.get("estimated_rows", 0)),
                    record.get("tags", ""),
                    record.get("view_name", ""),
                    record.get("partition_key", ""),
                    record.get("sample_sql", ""),
                    int(record.get("is_active", 1)),
                    self._now(),
                ),
            )
            self._conn.commit()
            self._rebuild_fts()
            return True
        except Exception as e:
            log.error("[MetadataIndex] upsert failed: %s", e)
            return False

    def bulk_upsert(self, records: List[dict]) -> int:
        """批量插入/更新，返回成功条数。"""
        count = 0
        for rec in records:
            if self.upsert(rec):
                count += 1
        return count

    def delete(self, table_name: str) -> bool:
        """软删除（标记为 inactive）。"""
        try:
            self._conn.execute(
                "UPDATE table_metadata SET is_active=0, updated_at=? WHERE table_name=?",
                (self._now(), table_name),
            )
            self._conn.commit()
            self._rebuild_fts()
            return True
        except Exception as e:
            log.error("[MetadataIndex] delete failed: %s", e)
            return False

    def get(self, table_name: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM table_metadata WHERE table_name=?", (table_name,)
        ).fetchone()
        return dict(row) if row else None

    def list_all(self, active_only: bool = True) -> List[dict]:
        if active_only:
            return self._rows(self._conn.execute(
                "SELECT * FROM table_metadata WHERE is_active=1 ORDER BY process_stage, table_name"
            ))
        return self._rows(self._conn.execute(
            "SELECT * FROM table_metadata ORDER BY process_stage, table_name"
        ))

    def list_by_stage(self, stage: str) -> List[dict]:
        return self._rows(self._conn.execute(
            "SELECT * FROM table_metadata WHERE process_stage=? AND is_active=1 ORDER BY table_name",
            (stage,),
        ))

    # ── FTS5 全文检索 ─────────────────────────────────────────────────────────

    def search(self, keywords: str, top_k: int = 5) -> List[dict]:
        """根据业务关键词搜索最相关的表，返回按相关性排序的结果。"""
        q = keywords.strip()
        if not q:
            return []

        # 尝试 FTS5 全文检索
        try:
            rows = self._rows(self._conn.execute(
                """SELECT m.*, rank
                   FROM table_metadata m
                   JOIN table_metadata_fts ON table_metadata_fts.rowid = m.id
                   WHERE table_metadata_fts MATCH ? AND m.is_active=1
                   ORDER BY rank
                   LIMIT ?""",
                (q, top_k),
            ))
            if rows:
                return rows
        except sqlite3.OperationalError:
            pass

        # FTS5 降级：拆分为多个关键词做 LIKE 模糊匹配
        # Two-level tokenization:
        # 1. Split by spaces/commas → each part is AND'd (e.g. "Array 点灯 不良率")
        # 2. For CJK tokens without spaces, generate bigrams OR'd with the original
        #    (e.g. "设备保养" → ("设备保养" OR "设备" OR "保养"))
        raw_tokens = [kw.strip() for kw in q.replace(",", " ").split() if kw.strip()]
        if not raw_tokens:
            return []

        # Build a list of (conditions, params) per space-separated token group
        # Groups are AND'd together; within a group, bigrams are OR'd
        all_group_conditions = []
        all_params = []

        for token in raw_tokens:
            # Collect all variants for this token: original + CJK bigrams
            variants = [token]
            cjk_chars = [c for c in token if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf']
            if len(cjk_chars) >= 3:
                for i in range(len(cjk_chars) - 1):
                    bigram = cjk_chars[i] + cjk_chars[i+1]
                    if bigram not in variants:
                        variants.append(bigram)

            # Within a group, variants are OR'd
            group_ors = []
            for v in variants:
                like = f"%{v}%"
                group_ors.append(
                    "(table_name LIKE ? OR business_name LIKE ? OR description LIKE ? OR tags LIKE ?)"
                )
                all_params.extend([like, like, like, like])

            all_group_conditions.append("(" + " OR ".join(group_ors) + ")")

        # Groups are AND'd
        where_clause = " AND ".join(all_group_conditions)

        rows = self._rows(self._conn.execute(
            f"""SELECT * FROM table_metadata
               WHERE is_active=1 AND {where_clause}
               ORDER BY
                   CASE WHEN table_name    LIKE ? THEN 0 ELSE 1 END,
                   CASE WHEN business_name LIKE ? THEN 0 ELSE 1 END,
                   CASE WHEN tags         LIKE ? THEN 0 ELSE 1 END
               LIMIT ?""",
            (*all_params, *([f"%{raw_tokens[0]}%"] * 3), top_k),
        ))
        return rows

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    def get_summary(self) -> str:
        """返回所有活跃表的摘要（仅表名 + 业务名 + 工序），用于 Agent 快速了解数据全景。"""
        rows = self.list_all(active_only=True)
        if not rows:
            return "暂无表元数据。请先导入表元数据。"
        lines = ["## 数据表全景（摘要）\n"]
        current_stage = ""
        for r in rows:
            stage = r.get("process_stage", "") or "其他"
            if stage != current_stage:
                lines.append(f"\n### {stage} 工序\n")
                current_stage = stage
            biz = r.get("business_name", "") or r.get("table_name", "")
            desc = r.get("description", "")
            rows_str = f" (~{r['estimated_rows']:,}行)" if r.get("estimated_rows") else ""
            if desc:
                lines.append(f"- **{biz}**{rows_str} — {desc}")
            else:
                lines.append(f"- **{biz}**{rows_str}")
        return "\n".join(lines)

    def format_search_result(self, results: List[dict]) -> str:
        """将搜索结果格式化为 LLM 易读的文本。"""
        if not results:
            return "未找到匹配的表。"
        lines = ["## 检索到的相关表\n"]
        for i, r in enumerate(results, 1):
            biz = r.get("business_name", "") or r.get("table_name", "")
            stage = r.get("process_stage", "") or "?"
            desc = r.get("description", "")
            keys = r.get("key_columns", "")
            sample = r.get("sample_sql", "")
            lines.append(f"{i}. **{biz}** (物理表: `{r['table_name']}`, 工序: {stage})")
            if desc:
                lines.append(f"   - 说明: {desc}")
            if keys:
                lines.append(f"   - 关键字段: {keys}")
            if sample:
                lines.append(f"   - 典型查询: `{sample}`")
            lines.append("")
        return "\n".join(lines)

    def _rebuild_fts(self) -> None:
        try:
            self._conn.execute(
                "INSERT INTO table_metadata_fts(table_metadata_fts) VALUES('rebuild')"
            )
            self._conn.commit()
        except Exception:
            pass

    def close(self) -> None:
        self._conn.close()


# ── 单例 ─────────────────────────────────────────────────────────────────────

_metadata_index: Optional[MetadataIndex] = None


def get_metadata_index() -> MetadataIndex:
    global _metadata_index
    if _metadata_index is None:
        _metadata_index = MetadataIndex()
    return _metadata_index
