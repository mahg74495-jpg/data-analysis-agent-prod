#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SPC Control Chart Analysis
==========================
Statistical Process Control for semiconductor manufacturing.
Calculates X-bar & R control limits, identifies out-of-control points,
and computes Western Electric rules violations.

Output tables:
  analysis_result     — Control limits and process summary
  analysis_breakdown  — Per-subgroup statistics with OC/rule flags
  analysis_metrics    — Process capability summary
"""
import numpy as np
import pandas as pd
from typing import Optional, Tuple

ANALYSIS_ID   = "SPC_Analysis"
ANALYSIS_NAME = "SPC 控制图分析（Control Chart）"
ANALYSIS_DESC = (
    "对半导体工艺参数执行统计过程控制（SPC）分析。"
    "计算 X-bar 和 R 控制限，识别超出控制限的点，"
    "并检测 Western Electric 规则违反（连续7点同侧/趋势等）。"
    "通过 target_column 指定量测值列，groupby_column 指定分组列（如腔室/设备），"
    "n_deciles 指定子组大小（默认 5）。"
)
REQUIRED_PARAMS = ["target_column"]
OPTIONAL_PARAMS = [
    "groupby_column (chamber/equipment grouping, optional)",
    "n_deciles (subgroup size, default 5)",
]
OUTPUT_TABLES = ["analysis_result", "analysis_breakdown", "analysis_metrics"]


def _western_electric_rules(values: np.ndarray, mean: float, sigma: float) -> list:
    """Check Western Electric rules and return list of violated rule descriptions."""
    violations = []
    n = len(values)
    if n < 8:
        return violations

    # Rule 1: One point beyond 3-sigma
    for i, v in enumerate(values):
        if abs(v - mean) > 3 * sigma:
            violations.append((i, f"Rule 1: Point {i} beyond 3-sigma (value={v:.3f})"))

    # Rule 2: 2 of 3 consecutive points beyond 2-sigma (same side)
    for i in range(n - 2):
        side = np.sign(values[i] - mean)
        if side == 0:
            continue
        count = sum(1 for j in range(3) if np.sign(values[i + j] - mean) == side and abs(values[i + j] - mean) > 2 * sigma)
        if count >= 2:
            violations.append((i, f"Rule 2: 2 of 3 points beyond 2-sigma at point {i}"))

    # Rule 3: 4 of 5 consecutive points beyond 1-sigma (same side)
    for i in range(n - 4):
        side = np.sign(values[i] - mean)
        if side == 0:
            continue
        count = sum(1 for j in range(5) if np.sign(values[i + j] - mean) == side and abs(values[i + j] - mean) > 1 * sigma)
        if count >= 4:
            violations.append((i, f"Rule 3: 4 of 5 points beyond 1-sigma at point {i}"))

    # Rule 4: 8 consecutive points on same side of centerline
    for i in range(n - 7):
        side = np.sign(values[i] - mean)
        if side == 0:
            continue
        if all(np.sign(values[i + j] - mean) == side for j in range(8)):
            violations.append((i, f"Rule 4: 8 consecutive points on same side at point {i}"))

    return violations


def run(
    df: pd.DataFrame,
    target_column: str,
    groupby_column: Optional[str] = None,
    n_deciles: int = 5,
) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    if target_column not in df.columns:
        raise ValueError(f"Column '{target_column}' not found.")

    subgroup_size = max(2, min(int(n_deciles), 20))
    values = df[target_column].dropna().values
    n = len(values)

    # Form subgroups
    n_subgroups = n // subgroup_size
    if n_subgroups < 2:
        raise ValueError(f"Need at least 2 subgroups (have {n} rows, subgroup_size={subgroup_size})")

    subgroups = values[:n_subgroups * subgroup_size].reshape(n_subgroups, subgroup_size)
    x_bars = subgroups.mean(axis=1)
    ranges = subgroups.ptp(axis=1)

    grand_mean = x_bars.mean()
    mean_range = ranges.mean()

    # Control chart constants for n=2..20
    A2_table = {2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483,
                7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308, 11: 0.285,
                12: 0.266, 13: 0.249, 14: 0.235, 15: 0.223, 16: 0.212,
                17: 0.203, 18: 0.194, 19: 0.187, 20: 0.180}
    D3_table = {2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0.076, 8: 0.136,
                9: 0.184, 10: 0.223, 11: 0.256, 12: 0.283, 13: 0.307,
                14: 0.328, 15: 0.347, 16: 0.363, 17: 0.378, 18: 0.391,
                19: 0.403, 20: 0.415}
    D4_table = {2: 3.267, 3: 2.575, 4: 2.282, 5: 2.115, 6: 2.004,
                7: 1.924, 8: 1.864, 9: 1.816, 10: 1.777, 11: 1.744,
                12: 1.717, 13: 1.693, 14: 1.672, 15: 1.653, 16: 1.637,
                17: 1.622, 18: 1.608, 19: 1.597, 20: 1.585}

    A2 = A2_table.get(subgroup_size, 0.577)
    D3 = D3_table.get(subgroup_size, 0)
    D4 = D4_table.get(subgroup_size, 2.115)

    # X-bar control limits
    ucl_x = grand_mean + A2 * mean_range
    lcl_x = grand_mean - A2 * mean_range
    # R control limits
    ucl_r = D4 * mean_range
    lcl_r = D3 * mean_range

    # Estimate sigma (using R-bar / d2)
    d2_table = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534,
                7: 2.704, 8: 2.847, 9: 2.970, 10: 3.078, 11: 3.173,
                12: 3.258, 13: 3.336, 14: 3.407, 15: 3.472, 16: 3.532,
                17: 3.588, 18: 3.640, 19: 3.689, 20: 3.735}
    d2 = d2_table.get(subgroup_size, 2.326)
    sigma_est = mean_range / d2

    # Check Western Electric rules
    violations = _western_electric_rules(x_bars, grand_mean, sigma_est / np.sqrt(subgroup_size))

    # Build result table
    result_rows = []
    for i in range(n_subgroups):
        oc_x = "OC" if (x_bars[i] > ucl_x or x_bars[i] < lcl_x) else ""
        oc_r = "OC" if (ranges[i] > ucl_r or ranges[i] < lcl_r) else ""
        result_rows.append({
            "subgroup": i + 1,
            "x_bar": round(x_bars[i], 4),
            "range": round(ranges[i], 4),
            "ucl_x_bar": round(ucl_x, 4),
            "lcl_x_bar": round(lcl_x, 4),
            "ucl_r": round(ucl_r, 4),
            "lcl_r": round(lcl_r, 4),
            "oc_x_bar": oc_x,
            "oc_r": oc_r,
        })
    result_df = pd.DataFrame(result_rows)

    # Metrics table
    metrics = pd.DataFrame([
        {"metric": "Grand Mean (X-bar)", "value": round(grand_mean, 4)},
        {"metric": "Mean Range (R-bar)", "value": round(mean_range, 4)},
        {"metric": "UCL (X-bar)", "value": round(ucl_x, 4)},
        {"metric": "LCL (X-bar)", "value": round(lcl_x, 4)},
        {"metric": "UCL (R)", "value": round(ucl_r, 4)},
        {"metric": "LCL (R)", "value": round(lcl_r, 4)},
        {"metric": "Estimated Sigma", "value": round(sigma_est, 4)},
        {"metric": "Subgroup Size", "value": subgroup_size},
        {"metric": "Number of Subgroups", "value": n_subgroups},
        {"metric": "OC Points (X-bar)", "value": sum(1 for r in result_rows if r["oc_x_bar"])},
        {"metric": "OC Points (R)", "value": sum(1 for r in result_rows if r["oc_r"])},
        {"metric": "Western Electric Violations", "value": len(violations)},
    ])
    metrics_df = pd.DataFrame(metrics)

    # Build markdown report
    md = f"""## SPC 控制图分析结果

### 控制限
| 统计量 | 数值 |
|---|---|
| 总均值 (X-bar) | {grand_mean:.4f} |
| 平均极差 (R-bar) | {mean_range:.4f} |
| X-bar UCL | {ucl_x:.4f} |
| X-bar LCL | {lcl_x:.4f} |
| R UCL | {ucl_r:.4f} |
| R LCL | {lcl_r:.4f} |
| 估计标准差 | {sigma_est:.4f} |

### 超出控制限的点
"""
    oc_points = [r for r in result_rows if r["oc_x_bar"] or r["oc_r"]]
    if oc_points:
        for r in oc_points:
            reasons = []
            if r["oc_x_bar"]:
                reasons.append(f"X-bar={r['x_bar']} (限: {r['lcl_x_bar']}~{r['ucl_x_bar']})")
            if r["oc_r"]:
                reasons.append(f"R={r['range']} (限: {r['lcl_r']}~{r['ucl_r']})")
            md += f"- 子组 {r['subgroup']}: {'; '.join(reasons)}\n"
    else:
        md += "- 无超出控制限的点，过程受控。\n"

    if violations:
        md += "\n### Western Electric 规则违反\n"
        for idx, desc in violations:
            md += f"- 子组 {idx + 1}: {desc}\n"

    return result_df, metrics_df, md
