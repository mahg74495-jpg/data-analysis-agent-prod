#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Virtual Metrology (VM) Analysis
================================
Predict metrology values from FDC (Fault Detection & Classification) parameters
using multiple regression models. All models are implemented from scratch
using only numpy/pandas.

Features:
  - Multiple linear regression (OLS)
  - Ridge regression (L2 regularization)
  - Feature importance analysis
  - Prediction vs actual comparison
  - Model accuracy metrics (R², RMSE, MAE, MAPE)

Output tables:
  analysis_result     — Model coefficients / feature importance
  analysis_breakdown  — Actual vs predicted values with residuals
  analysis_metrics    — Model performance metrics
"""
import numpy as np
import pandas as pd
from typing import Optional, Tuple

ANALYSIS_ID   = "Virtual_Metrology"
ANALYSIS_NAME = "虚拟量测分析（Virtual Metrology）"
ANALYSIS_DESC = (
    "使用 FDC 参数预测量测值（虚拟量测）。支持多元线性回归和岭回归，"
    "输出特征重要性、预测值与实际值对比、模型评估指标。"
    "通过 target_column 指定目标量测值列，groupby_column 指定正则化系数 lambda（默认 0.01），"
    "n_deciles 指定测试集比例（百分比，默认 30）。"
)
REQUIRED_PARAMS = ["target_column"]
OPTIONAL_PARAMS = [
    "groupby_column (ridge lambda, default 0.01)",
    "n_deciles (test_size %, default 30)",
]
OUTPUT_TABLES = ["analysis_result", "analysis_breakdown", "analysis_metrics"]

_DEFAULT_LAMBDA = 0.01
_DEFAULT_TEST_SIZE = 0.3
_MIN_ROWS = 20


def _standardize(X: np.ndarray) -> tuple:
    """Z-score standardization."""
    means = np.nanmean(X, axis=0)
    stds = np.nanstd(X, axis=0)
    stds[stds == 0] = 1.0
    return (X - means) / stds, means, stds


def run(
    df: pd.DataFrame,
    target_column: str,
    groupby_column: Optional[str] = None,
    n_deciles: int = 30,
) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    if target_column not in df.columns:
        raise ValueError(f"Column '{target_column}' not found.")

    # Parse parameters
    ridge_lambda = float(groupby_column) if groupby_column and groupby_column.replace('.', '').replace('-', '').isdigit() else _DEFAULT_LAMBDA
    test_size = max(0.1, min(0.5, int(n_deciles) / 100)) if n_deciles else _DEFAULT_TEST_SIZE

    # Prepare data: target = target_column, features = all numeric columns except target
    feature_cols = [c for c in df.columns if c != target_column and pd.api.types.is_numeric_dtype(df[c])]
    if not feature_cols:
        raise ValueError("No numeric feature columns found for virtual metrology prediction.")

    data = df[[target_column] + feature_cols].dropna()
    if len(data) < _MIN_ROWS:
        raise ValueError(f"Need at least {_MIN_ROWS} rows after dropping NA, got {len(data)}")

    y = data[target_column].values
    X = data[feature_cols].values
    n = len(data)

    # Train/test split
    indices = np.random.RandomState(42).permutation(n)
    n_test = max(1, int(n * test_size))
    test_idx = indices[:n_test]
    train_idx = indices[n_test:]

    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    # Standardize features
    X_train_s, means, stds = _standardize(X_train)
    X_test_s = (X_test - means) / stds

    # Add bias term
    X_train_b = np.c_[np.ones(X_train_s.shape[0]), X_train_s]
    X_test_b = np.c_[np.ones(X_test_s.shape[0]), X_test_s]

    # Ridge regression: beta = (X'X + lambda*I)^{-1} X'y
    n_features = X_train_b.shape[1]
    I = np.eye(n_features)
    I[0, 0] = 0  # Don't regularize bias
    beta = np.linalg.solve(X_train_b.T @ X_train_b + ridge_lambda * I, X_train_b.T @ y_train)

    # Predictions
    y_train_pred = X_train_b @ beta
    y_test_pred = X_test_b @ beta

    # Metrics
    ss_res_train = np.sum((y_train - y_train_pred) ** 2)
    ss_tot_train = np.sum((y_train - np.mean(y_train)) ** 2)
    r2_train = 1 - ss_res_train / ss_tot_train if ss_tot_train > 0 else 0

    ss_res_test = np.sum((y_test - y_test_pred) ** 2)
    ss_tot_test = np.sum((y_test - np.mean(y_test)) ** 2)
    r2_test = 1 - ss_res_test / ss_tot_test if ss_tot_test > 0 else 0

    rmse_train = np.sqrt(np.mean((y_train - y_train_pred) ** 2))
    rmse_test = np.sqrt(np.mean((y_test - y_test_pred) ** 2))
    mae_train = np.mean(np.abs(y_train - y_train_pred))
    mae_test = np.mean(np.abs(y_test - y_test_pred))

    # Feature importance (coefficients)
    coefs = beta[1:]  # exclude bias
    feature_importance = []
    for i, col in enumerate(feature_cols):
        feature_importance.append({
            "feature": col,
            "coefficient": round(coefs[i], 6),
            "abs_coef": round(abs(coefs[i]), 6),
            "importance_pct": 0.0,  # calculated below
        })
    total_abs = sum(f["abs_coef"] for f in feature_importance)
    if total_abs > 0:
        for f in feature_importance:
            f["importance_pct"] = round(f["abs_coef"] / total_abs * 100, 2)
    feature_importance.sort(key=lambda x: x["importance_pct"], reverse=True)
    result_df = pd.DataFrame(feature_importance)

    # Actual vs predicted
    breakdown_rows = []
    for i in range(len(y_test)):
        breakdown_rows.append({
            "index": int(test_idx[i]),
            "actual": round(y_test[i], 4),
            "predicted": round(y_test_pred[i], 4),
            "residual": round(y_test[i] - y_test_pred[i], 4),
            "abs_error_pct": round(abs(y_test[i] - y_test_pred[i]) / max(abs(y_test[i]), 0.001) * 100, 2),
        })
    breakdown_df = pd.DataFrame(breakdown_rows)

    # Metrics
    mape_train = np.mean(np.abs((y_train - y_train_pred) / np.maximum(np.abs(y_train), 0.001))) * 100
    mape_test = np.mean(np.abs((y_test - y_test_pred) / np.maximum(np.abs(y_test), 0.001))) * 100

    metrics = pd.DataFrame([
        {"metric": "R² (Train)", "value": round(r2_train, 4)},
        {"metric": "R² (Test)", "value": round(r2_test, 4)},
        {"metric": "RMSE (Train)", "value": round(rmse_train, 4)},
        {"metric": "RMSE (Test)", "value": round(rmse_test, 4)},
        {"metric": "MAE (Train)", "value": round(mae_train, 4)},
        {"metric": "MAE (Test)", "value": round(mae_test, 4)},
        {"metric": "MAPE (Train) %", "value": round(mape_train, 2)},
        {"metric": "MAPE (Test) %", "value": round(mape_test, 2)},
        {"metric": "Ridge Lambda", "value": ridge_lambda},
        {"metric": "Training Samples", "value": len(y_train)},
        {"metric": "Test Samples", "value": len(y_test)},
        {"metric": "Features Used", "value": len(feature_cols)},
    ])
    metrics_df = pd.DataFrame(metrics)

    # Markdown
    md = f"""## 虚拟量测（VM）分析结果

### 模型性能
| 指标 | 训练集 | 测试集 |
|---|---|---|
| R² | {r2_train:.4f} | {r2_test:.4f} |
| RMSE | {rmse_train:.4f} | {rmse_test:.4f} |
| MAE | {mae_train:.4f} | {mae_test:.4f} |
| MAPE | {mape_train:.2f}% | {mape_test:.2f}% |

### 模型评价
"""
    if r2_test >= 0.8:
        md += "- ✅ 模型预测能力优秀（R² ≥ 0.8）\n"
    elif r2_test >= 0.6:
        md += "- ⚠️ 模型预测能力可接受（0.6 ≤ R² < 0.8）\n"
    elif r2_test >= 0.4:
        md += "- 🔶 模型预测能力一般（0.4 ≤ R² < 0.6），建议增加更多 FDC 参数\n"
    else:
        md += "- ❌ 模型预测能力不足（R² < 0.4），需要重新选择特征\n"

    md += "\n### 特征重要性（Top 10）\n"
    for f in feature_importance[:10]:
        md += f"- {f['feature']}: 系数={f['coefficient']}, 贡献={f['importance_pct']}%\n"

    return result_df, breakdown_df, md
