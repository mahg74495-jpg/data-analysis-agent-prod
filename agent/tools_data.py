# -*- coding: utf-8 -*-
"""Mixin: data-oriented tools (schema, query, analysis, chart, clean, profile)."""
import re
import sqlite3


class DataToolsMixin:
    """All methods here rely on self.data_source, self._schema_cache,
    self.ppt_color_scheme — defined in BusinessAgent.__init__."""

    # ── Knowledge base lookup ─────────────────────────────────────────────────

    def _tool_query_knowledge(self, question: str) -> str:
        try:
            from Function.Knowledge.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()
            results = kb.search(question)
        except Exception as e:
            return f"Knowledge base unavailable: {e}"

        if not any(results.values()):
            return "No relevant knowledge found."

        lines: list[str] = []

        for m in results["metrics"]:
            lines.append(f"[Metric] {m['name']}")
            if m.get("alias"):
                lines.append(f"  Alias: {m['alias']}")
            if m.get("definition"):
                lines.append(f"  Definition: {m['definition']}")
            if m.get("sql_template"):
                lines.append(f"  SQL template: {m['sql_template']}")
            if m.get("notes"):
                lines.append(f"  Notes: {m['notes']}")

        for r in results["rules"]:
            lines.append(f"[Rule/{r['severity'].upper()}] {r['rule_id']}: {r['description']}")
            if r.get("condition"):
                lines.append(f"  Condition: {r['condition']}")

        for n in results["notes"]:
            lines.append(f"[Context] {n['topic']}: {n['content']}")

        return "\n".join(lines)

    # ── 元数据路由 ───────────────────────────────────────────────────────────

    def _tool_search_relevant_tables(self, keywords: str, top_k: int = 5) -> str:
        """根据业务关键词搜索最相关的物理表/视图。"""
        try:
            from data.metadata_index import get_metadata_index
            idx = get_metadata_index()
            results = idx.search(keywords, top_k=min(top_k, 10))
            return idx.format_search_result(results)
        except Exception as e:
            return f"[元数据检索失败] {e}"

    def _tool_get_table_summary(self) -> str:
        """返回所有表的全景摘要（仅表名+业务名+工序，不含列细节）。"""
        try:
            from data.metadata_index import get_metadata_index
            idx = get_metadata_index()
            return idx.get_summary()
        except Exception as e:
            return f"[全景摘要获取失败] {e}"

    # ── Basic data access ─────────────────────────────────────────────────────

    def _tool_get_schema(self, tables: list = None) -> str:
        if not self.data_source:
            return "No data source connected."
        if tables:
            # 指定表名：返回完整 schema
            return self.data_source.get_schema(tables=tables)
        # 无参数：返回摘要（仅表名列表）
        return self.data_source.get_schema(summary_only=True)

    def _tool_query_data(self, sql: str) -> str:
        if not self.data_source:
            return "No data source. Please connect a database or upload an Excel file first."

        # ── Query guardrails ──────────────────────────────────────────────
        sql_stripped = sql.strip().upper()

        # Rule 1: Block SELECT *
        if sql_stripped.startswith("SELECT *") or sql_stripped.startswith("SELECT  *"):
            return (
                "ERROR: SELECT * is not allowed. Specify columns explicitly. "
                "Example: SELECT glass_id, product_type, yield FROM array_production"
            )

        # Rule 2: Warn if no WHERE clause (for non-trivial tables)
        has_where = "WHERE" in sql_stripped
        has_limit = "LIMIT" in sql_stripped

        if not has_where and not has_limit:
            return (
                "ERROR: Query must include a WHERE filter (time range / lot / batch) "
                "or a LIMIT clause to prevent full table scans."
            )

        # Rule 3: Auto-append LIMIT if missing
        if not has_limit:
            sql = sql.rstrip(";") + " LIMIT 200"

        df, error = self.data_source.execute_query(sql)
        if error:
            return f"SQL Error: {error}"
        return self.data_source.format_result(df)

    # ── 聚合查询工具（替代明细查询） ───────────────────────────────────────

    def _tool_get_column_distribution(self, table: str, column: str, where: str = "") -> str:
        """获取列分布统计，不返回明细行。"""
        if not self.data_source:
            return "No data source connected."

        where_clause = f" WHERE {where}" if where else ""

        stats_sql = (
            "SELECT COUNT(*) as total_rows, COUNT(" + column + ") as non_null, "
            "COUNT(*) - COUNT(" + column + ") as null_count, "
            "MIN(" + column + ") as min_val, MAX(" + column + ") as max_val, "
            "AVG(" + column + ") as avg_val, STDDEV(" + column + ") as std_val "
            'FROM "' + table + '"' + where_clause
        )
        df_stats, err = self.data_source.execute_query(stats_sql)
        if err:
            return f"Error computing distribution: {err}"

        lines = [f"Column: {column}  (Table: {table})"]
        if not df_stats.empty:
            row = df_stats.iloc[0]
            lines.append(f"  Total rows: {row['total_rows']}")
            lines.append(f"  Non-null:   {row['non_null']}")
            lines.append(f"  Null count: {row['null_count']}")
            if row['min_val'] is not None:
                lines.append(f"  Min: {row['min_val']}")
                lines.append(f"  Max: {row['max_val']}")
                lines.append(f"  Avg: {row['avg_val']}")
                lines.append(f"  Std: {row['std_val']}")

        top_sql = (
            "SELECT " + column + " as value, COUNT(*) as freq "
            'FROM "' + table + '"' + where_clause + " "
            "WHERE " + column + " IS NOT NULL "
            "GROUP BY " + column + " "
            "ORDER BY freq DESC LIMIT 5"
        )
        df_top, _ = self.data_source.execute_query(top_sql)
        if not df_top.empty:
            lines.append("  Top 5 values:")
            for _, r in df_top.iterrows():
                pct = r['freq'] / df_stats.iloc[0]['total_rows'] * 100 if not df_stats.empty else 0
                lines.append(f"    {r['value']}: {r['freq']} ({pct:.1f}%)")

        return "\n".join(lines)

    def _tool_get_aggregated_metrics(
        self, table: str, group_by: str, metrics: str,
        where: str = "", order_by: str = "", limit: int = 50
    ) -> str:
        """按分组聚合计算指标，返回汇总结果。"""
        if not self.data_source:
            return "No data source connected."

        where_clause = f" WHERE {where}" if where else ""
        order_clause = f" ORDER BY {order_by}" if order_by else ""
        limit = min(max(1, limit), 200)

        sql = (
            "SELECT " + group_by + ", " + metrics + " "
            'FROM "' + table + '"' + where_clause + " "
            "GROUP BY " + group_by + " "
            + order_clause + " "
            "LIMIT " + str(limit)
        )

        df, err = self.data_source.execute_query(sql)
        if err:
            return f"Error computing aggregated metrics: {err}"
        if df.empty:
            return "No results."

        return self.data_source.format_result(df)

    def _tool_create_analysis_table(self, sql: str, table_name: str = "analysis_data") -> str:
        if not self.data_source:
            return "No data source connected."
        result = self.data_source.create_analysis_table(sql, table_name)
        self._schema_cache = None
        return result

    # ── DataFrame → DataSource writer (backward-compatible) ──────────────────

    def _write_analysis_df(self, df, table_name: str) -> None:
        """Write df into the connected data source as a queryable table.

        Tries the new connector API first; falls back to direct SQLite write
        for older connector.py versions that lack the _df parameter.
        """
        ds = self.data_source

        try:
            ds.create_analysis_table(sql=None, table_name=table_name, _df=df)
            self._schema_cache = None
            return
        except TypeError:
            pass  # old connector — fall through to direct SQLite write

        conn = getattr(ds, "_conn", None)
        if conn is None:
            if getattr(ds, "_cache_conn", None) is None:
                ds._cache_conn = sqlite3.connect(":memory:", check_same_thread=False)
                ds._cache_tables = set()
            conn = ds._cache_conn
            ds._cache_tables.add(table_name)

        df.to_sql(table_name, conn, if_exists="replace", index=False)
        self._schema_cache = None

    # ── Analysis tool ─────────────────────────────────────────────────────────

    def _tool_run_analysis(
        self,
        analysis_name: str,
        sql: str,
        target_column: str,
        groupby_column: str = "",
        n_deciles: int = 10,
    ) -> str:
        if not self.data_source:
            return "No data source connected."

        df, error = self.data_source.execute_query(sql)
        if error:
            return f"SQL Error while fetching data: {error}"
        if df.empty:
            return "Query returned no rows — cannot run analysis."

        try:
            from Function.Analyze.registry import get as get_analysis
            entry = get_analysis(analysis_name)
        except KeyError as exc:
            return str(exc)
        except Exception as exc:
            return f"Failed to load analysis module '{analysis_name}': {exc}"

        run_fn = entry.get("run")
        if run_fn is None:
            return f"Analysis module '{analysis_name}' failed to load."

        try:
            ret = run_fn(
                df=df,
                target_column=target_column,
                groupby_column=groupby_column or None,
                n_deciles=n_deciles,
            )
        except Exception as exc:
            return f"Analysis error: {exc}"

        if len(ret) == 4:
            result_df, breakdown_df, extra_df, markdown = ret
        else:
            result_df, breakdown_df, markdown = ret
            extra_df = None

        try:
            _out_tbls = entry.get("output_tables", [])
            self._write_analysis_df(result_df, "analysis_result")
            if not breakdown_df.empty:
                self._write_analysis_df(breakdown_df, "analysis_breakdown")
            # Always write the third table so LLM SQL queries don't fail on missing table.
            # Write an empty-but-structured DataFrame when the result is empty.
            if extra_df is not None:
                extra_table_name = _out_tbls[2] if len(_out_tbls) > 2 else "analysis_extra"
                self._write_analysis_df(extra_df, extra_table_name)
        except Exception as exc:
            return (
                markdown
                + f"\n\n⚠️ **结果表写入失败**：{exc}\n"
                "分析计算已完成，但结果无法存为可查询表格，请联系开发者。"
            )

        if analysis_name == "K_Means" and "cluster" in breakdown_df.columns:
            markdown += self._kmeans_build_labeled(sql, breakdown_df)

        if analysis_name == "Data_Decile_Analysis" and "decile" in result_df.columns:
            markdown += self._decile_build_labeled(sql, target_column, n_deciles)

        return markdown

    def _kmeans_build_labeled(self, sql: str, breakdown_df) -> str:
        try:
            labeled_sql = re.sub(
                r"(?is)\bSELECT\b.+?\bFROM\b",
                "SELECT *\nFROM",
                sql,
                count=1,
            )
            full_df, err = self.data_source.execute_query(labeled_sql)
            if err or full_df.empty:
                return ""
            if len(full_df) != len(breakdown_df):
                return ""

            labeled_df = full_df.copy().reset_index(drop=True)
            labeled_df["cluster"] = breakdown_df["cluster"].values
            self._write_analysis_df(labeled_df, "cluster_labels")
            self._schema_cache = None

            cols_preview = ", ".join(str(c) for c in labeled_df.columns[:8])
            if len(labeled_df.columns) > 8:
                cols_preview += ", ..."
            return (
                "\n\n---\n"
                "### 📌 数据标签表 `cluster_labels`\n"
                f"已将聚类结果（cluster 列）回写到原始数据，"
                f"生成包含所有原始字段的标签表：\n\n"
                f"**列：** `{cols_preview}`\n\n"
                "可直接用于后续分析，例如：\n"
                "```sql\n"
                "-- 查看各簇的详细记录\n"
                "SELECT * FROM cluster_labels WHERE cluster = 0 LIMIT 20\n\n"
                "-- 统计各簇某字段的均值\n"
                "SELECT cluster, AVG(target_col) AS avg_val FROM cluster_labels GROUP BY cluster\n"
                "```"
            )
        except Exception:
            return ""

    def _decile_build_labeled(self, sql: str, target_column: str, n_deciles: int) -> str:
        """回写十分位标签到原始数据，生成 decile_labels 表。"""
        try:
            labeled_sql = re.sub(
                r"(?is)\bSELECT\b.+?\bFROM\b",
                "SELECT *\nFROM",
                sql,
                count=1,
            )
            full_df, err = self.data_source.execute_query(labeled_sql)
            if err or full_df.empty:
                return ""

            import pandas as pd
            col = full_df[target_column]
            # 用与 analyze.py 完全一致的逻辑重新打标签
            raw_cut = pd.qcut(
                pd.to_numeric(col, errors="coerce"),
                q=n_deciles,
                duplicates="drop",
            )
            ordered_cats = raw_cut.cat.categories
            cat_to_int = {cat: i + 1 for i, cat in enumerate(ordered_cats)}
            decile_int = raw_cut.map(cat_to_int)
            actual_n = int(decile_int.nunique())

            labeled_df = full_df.copy().reset_index(drop=True)
            labeled_df["decile"] = decile_int.values
            # 生成可读标签，如 "D01 (低)" / "D10 (高)"
            width = len(str(actual_n))
            def _label(d):
                if pd.isna(d):
                    return None
                d = int(d)
                if d == 1:
                    suffix = "（最低）"
                elif d == actual_n:
                    suffix = "（最高）"
                else:
                    suffix = ""
                return f"D{str(d).zfill(width)}{suffix}"
            labeled_df["decile_label"] = labeled_df["decile"].map(_label)

            self._write_analysis_df(labeled_df, "decile_labels")
            self._schema_cache = None

            cols_preview = ", ".join(str(c) for c in labeled_df.columns[:8])
            if len(labeled_df.columns) > 8:
                cols_preview += ", ..."
            return (
                "\n\n---\n"
                "### 📌 数据标签表 `decile_labels`\n"
                f"已将十分位标签（`decile` + `decile_label`）回写到原始数据，"
                f"共 {len(labeled_df)} 行：\n\n"
                f"**列：** `{cols_preview}`\n\n"
                "可直接导出或用于进一步分析，例如：\n"
                "```sql\n"
                "-- 查看某分位的原始记录\n"
                f"SELECT * FROM decile_labels WHERE decile = 10 LIMIT 20\n\n"
                "-- 各分位均值汇总\n"
                f"SELECT decile, decile_label, AVG({target_column}) AS avg_val\n"
                "FROM decile_labels GROUP BY decile, decile_label ORDER BY decile\n"
                "```"
            )
        except Exception:
            return ""

    # ── Chart selector ────────────────────────────────────────────────────────

    def _tool_select_chart(self, user_intent: str, available_columns: list = None) -> str:
        """Query the embedded chart registry and return ranked candidates with exact field_mapping specs."""
        try:
            from LLM.chart_selector import select_charts, format_selection_result
            cols = list(available_columns or [])
            # Auto-enrich with schema column names when the caller didn't supply them
            if not cols and self.data_source:
                schema = self._tool_get_schema()
                cols = re.findall(r"^\s{2,4}(\w+)\b", schema, re.MULTILINE)
            candidates = select_charts(user_intent, cols, top_n=3)
            return format_selection_result(candidates)
        except Exception as exc:
            return f"Chart selection error: {exc}"

    # ── Chart tool ────────────────────────────────────────────────────────────

    def _tool_generate_chart(
        self, chart_type: str, sql: str, field_mapping: dict, title: str = ""
    ) -> dict:
        if not self.data_source:
            return {"error": "No data source connected."}
        df, error = self.data_source.execute_query(sql)
        if error:
            return {"error": f"Data query failed: {error}"}
        if df.empty:
            return {"error": "Query returned no rows — cannot generate chart."}

        from chart_generate import generate_chart as _gen

        options = {"title": title} if title else {}
        result = _gen(
            df=df,
            chart_type=chart_type,
            mapping=field_mapping,
            options=options,
            color_scheme=self.ppt_color_scheme,
        )
        if "error" in result:
            return {"error": result["error"]}
        return {"html": result.get("html", ""), "chart_type": chart_type}

    # ── Table discovery helpers ───────────────────────────────────────────────

    def _discover_all_tables(self) -> list:
        if not self.data_source:
            return []
        # Preferred: connector.list_tables() — returns ALL tables incl. runtime
        # analysis/derived tables (DuckDB information_schema based).
        list_fn = getattr(self.data_source, "list_tables", None)
        if callable(list_fn):
            try:
                tables = list_fn()
                if tables:
                    return list(tables)
            except Exception:
                pass
        # Fallback: parse the schema text (works for any connector).
        schema = self._tool_get_schema()
        return re.findall(r"^Table:\s+(\S+)", schema, re.MULTILINE)

    def _get_first_raw_table(self) -> str:
        tables = self._discover_all_tables()
        raw = [t for t in tables if not t.startswith("analysis_") and t != "cleaned_data"]
        return raw[0] if raw else (tables[0] if tables else "")

    # ── Profile & clean ───────────────────────────────────────────────────────

    def _tool_profile_data(self, table_name: str = "", columns: list = None) -> dict:
        if not self.data_source:
            return {"text": "❌ 请先连接数据源。", "charts": []}

        tname = table_name or self._get_first_raw_table()
        if not tname:
            return {"text": "❌ 数据源中没有可用的表格。", "charts": []}

        df, err = self.data_source.execute_query(f'SELECT * FROM "{tname}"')
        if err or df is None or df.empty:
            return {"text": f"❌ 读取表 '{tname}' 失败：{err}", "charts": []}

        try:
            from Function.Clean.data_profile import profile
            text, charts = profile(df, columns or None)
            return {"text": f"### 数据概况 · `{tname}`\n\n" + text, "charts": charts}
        except Exception as exc:
            return {"text": f"❌ 数据概况生成失败：{exc}", "charts": []}

    def _tool_clean_data(
        self,
        operation: str,
        table_name: str = "",
        columns=None,
        fill_method: str = "mean",
        lower_pct: float = 1.0,
        upper_pct: float = 99.0,
        trim_column: str = "",
        min_val=None,
        max_val=None,
        output_table: str = "cleaned_data",
    ) -> str:
        if not self.data_source:
            return "❌ 请先连接数据源。"

        tname = table_name or self._get_first_raw_table()
        if not tname:
            return "❌ 数据源中没有可用的表格。"

        df, err = self.data_source.execute_query(f'SELECT * FROM "{tname}"')
        if err or df is None or df.empty:
            return f"❌ 读取表 '{tname}' 失败：{err}"

        try:
            if operation == "fill_na":
                from Function.Clean.missing_handler import fill_missing
                cleaned_df, summary = fill_missing(df, fill_method, columns)
            elif operation == "winsorize":
                from Function.Clean.winsorize import winsorize
                cleaned_df, summary = winsorize(df, lower_pct, upper_pct, columns)
            elif operation == "trimming":
                if not trim_column:
                    return "❌ trimming 操作需要指定 trim_column。"
                if min_val is None or max_val is None:
                    return "❌ trimming 操作需要同时指定 min_val 和 max_val。"
                from Function.Clean.trimming import trim
                cleaned_df, summary = trim(df, trim_column, float(min_val), float(max_val))
            else:
                return f"❌ 未知操作 '{operation}'，支持：fill_na / winsorize / trimming"
        except Exception as exc:
            return f"❌ 清洗失败：{exc}"

        try:
            self._write_analysis_df(cleaned_df, output_table)
            self._schema_cache = None
        except Exception as exc:
            return summary + f"\n\n⚠️ 结果表写入失败：{exc}"

        return (
            summary
            + f"\n\n✅ 清洗结果已保存为表 `{output_table}`，可直接用于后续分析和图表生成。"
        )
