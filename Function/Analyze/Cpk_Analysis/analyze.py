#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cpk / Ppk Process Capability Analysis
======================================
Calculates process capability indices for semiconductor manufacturing:
  - Cp, Cpk (short-term, within-subgroup)
  - Pp, Ppk (long-term, overall)
  - Estimated sigma, PPM defect rate
  - Capability histogram with specification limits

Output tables:
  analysis_result     — Capability indices summary
  analysis_breakdown  — Per-group capability (when groupby_column is set)
  analysis_metrics    — Detailed statistics
"""
import numpy as np
import pandas as pd
from typing import Optional, Tuple

ANALYSIS_ID   = "Cpk_Analysis"
ANALYSIS_NAME = "过程能力分析（Cpk/Ppk）"
ANALYSIS_DESC = (
    "计算半导体工艺的过程能力指数 Cp/Cpk/Pp/Ppk。"
    "需要目标列（量测值）、规格上限 USL 和规格下限 LSL。"
    "通过 target_column 指定量测值列，groupby_column 指定分组列（如腔室/设备），"
    "n_deciles 传入 USL（规格上限），OPTIONAL_PARAMS 中的 n_deciles 同时作为 USL。"
)
REQUIRED_PARAMS = ["target_column"]
OPTIONAL_PARAMS = [
    "groupby_column (chamber/equipment grouping, optional)",
    "n_deciles (USL: upper spec limit, default auto-detect from data * 1.2)",
]
OUTPUT_TABLES = ["analysis_result", "analysis_breakdown", "analysis_metrics"]


def _compute_capability(values: np.ndarray, usl: float, lsl: float, label: str = "") -> dict:
    """Compute capability indices for a set of values."""
    n = len(values)
    mean = np.mean(values)
    std = np.std(values, ddof=1)  # sample std for Pp/Ppk
    std_within = np.std(values, ddof=0)  # population std for Cp/Cpk approximation

    if std == 0:
        return {"group": label, "n": n, "mean": mean, "std": 0,
                "cp": float('inf'), "cpk": float('inf'),
                "pp": float('inf'), "ppk": float('inf'),
                "ppm_above": 0, "ppm_below": 0, "ppm_total": 0}

    cp = (usl - lsl) / (6 * std) if usl > lsl else 0
    cpu = (usl - mean) / (3 * std)
    cpl = (mean - lsl) / (3 * std)
    cpk = min(cpu, cpl)

    pp = (usl - lsl) / (6 * std_within) if usl > lsl else 0
    ppu = (usl - mean) / (3 * std_within)
    ppl = (mean - lsl) / (3 * std_within)
    ppk = min(ppu, ppl)

    from scipy import stats as _stats
    ppm_above = (1 - _stats.norm.cdf((usl - mean) / std)) * 1e6
    ppm_below = _stats.norm.cdf((lsl - mean) / std) * 1e6

    return {
        "group": label, "n": int(n), "mean": round(mean, 4),
        "std": round(std, 4), "cp": round(cp, 4), "cpk": round(cpk, 4),
        "cpu": round(cpu, 4), "cpl": round(cpl, 4),
        "pp": round(pp, 4), "ppk": round(ppk, 4),
        "ppu": round(ppu, 4), "ppl": round(ppl, 4),
        "ppm_above": int(round(ppm_above)),
        "ppm_below": int(round(ppm_below)),
        "ppm_total": int(round(ppm_above + ppm_below)),
    }


def run(
    df: pd.DataFrame,
    target_column: str,
    groupby_column: Optional[str] = None,
    n_deciles: int = 0,
) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    if target_column not in df.columns:
        raise ValueError(f"Column '{target_column}' not found.")

    values = df[target_column].dropna().values
    if len(values) < 10:
        raise ValueError(f"Need at least 10 data points, got {len(values)}")

    # Auto-detect spec limits
    usl = float(n_deciles) if n_deciles > 0 else float(np.percentile(values, 99.9) * 1.1)
    lsl = 0.0  # Default LSL = 0 for most semiconductor parameters

    if groupby_column and groupby_column in df.columns:
        groups = df.groupby(groupby_column)[target_column]
        results = []
        for name, grp_values in groups:
            vals = grp_values.dropna().values
            if len(vals) >= 5:
                results.append(_compute_capability(vals, usl, lsl, str(name)))
        overall = _compute_capability(values, usl, lsl, "Overall")
        results.insert(0, overall)
    else:
        results = [_compute_capability(values, usl, lsl, "Overall")]

    result_df = pd.DataFrame(results)

    # Detailed metrics
    metrics = pd.DataFrame([
        {"metric": "Specification Upper Limit (USL)", "value": usl},
        {"metric": "Specification Lower Limit (LSL)", "value": lsl},
        {"metric": "Overall Mean", "value": round(float(np.mean(values)), 4)},
        {"metric": "Overall Std Dev", "value": round(float(np.std(values, ddof=1)), 4)},
        {"metric": "Min", "value": round(float(np.min(values)), 4)},
        {"metric": "Max", "value": round(float(np.max(values)), 4)},
        {"metric": "P25", "value": round(float(np.percentile(values, 25)), 4)},
        {"metric": "P50 (Median)", "value": round(float(np.median(values)), 4)},
        {"metric": "P75", "value": round(float(np.percentile(values, 75)), 4)},
        {"metric": "Data Points", "value": len(values)},
    ])
    metrics_df = pd.DataFrame(metrics)

    # Markdown report
    overall = results[0]
    md = f"""## 过程能力分析结果

### 规格限
- USL: {usl}
- LSL: {lsl}

### 整体能力指数
| 指数 | 数值 | 评价 |
|---|---|---|
| Cp | {overall['cp']} | {'✅ 合格' if overall['cp'] >= 1.33 else '⚠️ 不足' if overall['cp'] >= 1.0 else '❌ 不合格'} |
| Cpk | {overall['cpk']} | {'✅ 合格' if overall['cpk'] >= 1.33 else '⚠️ 不足' if overall['cpk'] >= 1.0 else '❌ 不合格'} |
| Pp | {overall['pp']} | {'✅ 合格' if overall['pp'] >= 1.33 else '⚠️ 不足' if overall['pp'] >= 1.0 else '❌ 不合格'} |
| Ppk | {overall['ppk']} | {'✅ 合格' if overall['ppk'] >= 1.33 else '⚠️ 不足' if overall['ppk'] >= 1.0 else '❌ 不合格'} |

### 预估缺陷率
- 超出 USL: {overall['ppm_above']:,} PPM
- 低于 LSL: {overall['ppm_below']:,} PPM
- 总缺陷率: {overall['ppm_total']:,} PPM
"""
    if len(results) > 1:
        md += "\n### 分组能力对比\n| 分组 | Cp | Cpk | Pp | Ppk | PPM |\n|---|---|---|---|---|---|\n"
        for r in results:
            md += f"| {r['group']} | {r['cp']} | {r['cpk']} | {r['pp']} | {r['ppk']} | {r['ppm_total']:,} |\n"

    return result_df, metrics_df, md
