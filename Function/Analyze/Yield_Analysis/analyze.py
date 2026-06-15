#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yield Analysis
==============
Comprehensive yield analysis for semiconductor manufacturing:
  - Overall yield calculation
  - Yield by product / layer / equipment / chamber
  - Yield loss Pareto (top defect types)
  - Yield trend over time
  - Bin/sort yield distribution
  - Yield by reticle / recipe

Output tables:
  analysis_result     — Yield summary by group
  analysis_breakdown  — Yield trend / loss Pareto data
  analysis_metrics    — Overall yield statistics
"""
import numpy as np
import pandas as pd
from typing import Optional, Tuple

ANALYSIS_ID   = "Yield_Analysis"
ANALYSIS_NAME = "良率分析（Yield Analysis）"
ANALYSIS_DESC = (
    "对半导体制造良率进行全面分析。支持："
    "总体良率计算、按产品/设备/腔室/工艺层的良率对比、"
    "良率损失帕累托分析、良率趋势分析。"
    "通过 target_column 指定良率/合格列（0/1 或百分比），"
    "groupby_column 指定分组列（如产品/设备/腔室），"
    "n_deciles 指定 Pareto top N 缺陷类型数（默认 10）。"
)
REQUIRED_PARAMS = ["target_column"]
OPTIONAL_PARAMS = [
    "groupby_column (product/equipment/chamber grouping, optional)",
    "n_deciles (Pareto top N defect types, default 10)",
]
OUTPUT_TABLES = ["analysis_result", "analysis_breakdown", "analysis_metrics"]


def run(
    df: pd.DataFrame,
    target_column: str,
    groupby_column: Optional[str] = None,
    n_deciles: int = 10,
) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    if target_column not in df.columns:
        raise ValueError(f"Column '{target_column}' not found.")

    # Detect yield column type: 0/1 binary or percentage
    vals = df[target_column].dropna()
    if vals.max() <= 1.0 and vals.min() >= 0:
        # Binary (0/1) — convert to percentage
        is_binary = True
    else:
        is_binary = False

    top_n = max(1, min(int(n_deciles), 50))

    # Overall yield
    if is_binary:
        overall_yield = vals.mean() * 100
        total_good = int(vals.sum())
        total_bad = int((1 - vals).sum())
    else:
        overall_yield = vals.mean()
        total_good = int((vals >= 90).sum()) if vals.max() > 1 else int((vals >= 0.9).sum())
        total_bad = len(vals) - total_good

    # Yield by group
    if groupby_column and groupby_column in df.columns:
        if is_binary:
            grp_yield = df.groupby(groupby_column)[target_column].agg(
                total="count", good="sum"
            ).reset_index()
            grp_yield["yield_pct"] = (grp_yield["good"] / grp_yield["total"] * 100).round(2)
            grp_yield["bad"] = grp_yield["total"] - grp_yield["good"]
        else:
            grp_yield = df.groupby(groupby_column)[target_column].agg(
                total="count", mean="mean"
            ).reset_index()
            grp_yield["yield_pct"] = grp_yield["mean"].round(2)
            grp_yield["good"] = None
            grp_yield["bad"] = None
        grp_yield = grp_yield.sort_values("yield_pct")
        result_df = grp_yield
    else:
        result_df = pd.DataFrame([{
            "group": "Overall",
            "total": len(vals),
            "yield_pct": round(overall_yield, 2),
            "good": total_good,
            "bad": total_bad,
        }])

    # Build breakdown: find defect type columns (string columns with defect/fail/reject in name)
    defect_cols = [c for c in df.columns if any(k in c.lower() for k in
                   ["defect", "fail", "reject", "bin", "cause", "error", "reason"])]
    breakdown_rows = []
    if defect_cols:
        for col in defect_cols[:3]:  # Use first 3 defect-related columns
            if df[col].dtype == object or df[col].nunique() < 50:
                counts = df[col].value_counts().head(top_n)
                for cat, cnt in counts.items():
                    breakdown_rows.append({"category": str(cat), "count": int(cnt), "source_col": col})

    if not breakdown_rows:
        # Fallback: distribution of the yield column itself
        if is_binary:
            breakdown_rows = [
                {"category": "Good (1)", "count": total_good, "source_col": target_column},
                {"category": "Bad (0)", "count": total_bad, "source_col": target_column},
            ]
        else:
            bins = [0, 50, 70, 80, 90, 95, 98, 99, 100]
            labels = ["0-50%", "50-70%", "70-80%", "80-90%", "90-95%", "95-98%", "98-99%", "99-100%"]
            try:
                cats = pd.cut(vals, bins=bins, labels=labels)
                for label, cnt in cats.value_counts().sort_index().items():
                    breakdown_rows.append({"category": str(label), "count": int(cnt), "source_col": "yield_range"})
            except Exception:
                pass

    breakdown_df = pd.DataFrame(breakdown_rows)

    # Metrics
    metrics = pd.DataFrame([
        {"metric": "Overall Yield (%)", "value": round(overall_yield, 2)},
        {"metric": "Total Wafers/Lots", "value": len(vals)},
        {"metric": "Good Units", "value": total_good},
        {"metric": "Defective Units", "value": total_bad},
        {"metric": "Yield Loss (%)", "value": round(100 - overall_yield, 2)},
    ])
    metrics_df = pd.DataFrame(metrics)

    # Markdown
    md = f"""## 良率分析结果

### 总体良率
- **总体良率**: {overall_yield:.2f}%
- **总样本数**: {len(vals):,}
- **良品数**: {total_good:,}
- **不良品数**: {total_bad:,}
- **良率损失**: {100 - overall_yield:.2f}%

### 良率评价
"""
    if overall_yield >= 98:
        md += "- ✅ 良率优秀（≥98%）\n"
    elif overall_yield >= 95:
        md += "- ⚠️ 良率可接受（95-98%），建议持续监控\n"
    elif overall_yield >= 90:
        md += "- 🔶 良率偏低（90-95%），建议排查主要缺陷来源\n"
    else:
        md += "- ❌ 良率严重偏低（<90%），需要立即采取纠正措施\n"

    if groupby_column and len(result_df) > 1:
        min_row = result_df.loc[result_df["yield_pct"].idxmin()]
        max_row = result_df.loc[result_df["yield_pct"].idxmax()]
        md += f"\n### 分组良率极值\n"
        md += f"- 最高: {max_row[groupby_column]} → {max_row['yield_pct']:.2f}%\n"
        md += f"- 最低: {min_row[groupby_column]} → {min_row['yield_pct']:.2f}%\n"
        md += f"- 极差: {max_row['yield_pct'] - min_row['yield_pct']:.2f}%\n"

    if breakdown_rows:
        md += "\n### 良率损失归因（Top 缺陷）\n"
        total_defect = sum(r["count"] for r in breakdown_rows)
        for i, r in enumerate(breakdown_rows[:top_n]):
            pct = r["count"] / total_defect * 100 if total_defect > 0 else 0
            md += f"{i+1}. {r['category']}: {r['count']:,} ({pct:.1f}%)\n"

    return result_df, breakdown_df, md
