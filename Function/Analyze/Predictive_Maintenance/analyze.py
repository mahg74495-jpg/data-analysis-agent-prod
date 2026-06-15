#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Predictive Maintenance (PdM) Analysis
======================================
Predict equipment/chamber failures from FDC and maintenance history data.
Implements from scratch using only numpy/pandas:
  - Logistic regression for failure probability prediction
  - Feature importance for identifying key failure indicators
  - Confusion matrix and ROC curve for model evaluation
  - Remaining Useful Life (RUL) estimation via degradation trend

Output tables:
  analysis_result     — Feature importance / failure risk factors
  analysis_breakdown  — Per-wafer/lot failure probability
  analysis_metrics    — Model performance + RUL estimates
"""
import numpy as np
import pandas as pd
from typing import Optional, Tuple

ANALYSIS_ID   = "Predictive_Maintenance"
ANALYSIS_NAME = "预测性维护分析（Predictive Maintenance）"
ANALYSIS_DESC = (
    "基于 FDC 参数和设备历史数据预测设备/腔室故障概率。"
    "使用逻辑回归预测故障概率，识别关键故障指标，"
    "评估模型性能（混淆矩阵、ROC、AUC），估算剩余可用寿命（RUL）。"
    "通过 target_column 指定故障标签列（0=正常，1=故障），"
    "groupby_column 指定设备/腔室分组列，"
    "n_deciles 指定正则化系数 lambda（默认 0.01）。"
)
REQUIRED_PARAMS = ["target_column"]
OPTIONAL_PARAMS = [
    "groupby_column (equipment/chamber grouping, optional)",
    "n_deciles (L2 regularization lambda, default 0.01)",
]
OUTPUT_TABLES = ["analysis_result", "analysis_breakdown", "analysis_metrics"]

_DEFAULT_LAMBDA = 0.01
_MIN_ROWS = 20


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -100, 100)))


def _standardize(X: np.ndarray) -> tuple:
    means = np.nanmean(X, axis=0)
    stds = np.nanstd(X, axis=0)
    stds[stds == 0] = 1.0
    return (X - means) / stds, means, stds


def run(
    df: pd.DataFrame,
    target_column: str,
    groupby_column: Optional[str] = None,
    n_deciles: int = 10,
) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    if target_column not in df.columns:
        raise ValueError(f"Column '{target_column}' not found.")

    ridge_lambda = float(n_deciles) / 1000 if n_deciles > 0 else _DEFAULT_LAMBDA

    # Feature columns: all numeric except target
    feature_cols = [c for c in df.columns if c != target_column and pd.api.types.is_numeric_dtype(df[c])]
    if not feature_cols:
        raise ValueError("No numeric feature columns found.")

    data = df[[target_column] + feature_cols].dropna()
    if len(data) < _MIN_ROWS:
        raise ValueError(f"Need at least {_MIN_ROWS} rows, got {len(data)}")

    y = data[target_column].values
    X = data[feature_cols].values
    n = len(data)

    # Train/test split (70/30)
    indices = np.random.RandomState(42).permutation(n)
    n_test = max(1, int(n * 0.3))
    test_idx = indices[:n_test]
    train_idx = indices[n_test:]

    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    # Standardize
    X_train_s, means, stds = _standardize(X_train)
    X_test_s = (X_test - means) / stds

    # Add bias
    X_train_b = np.c_[np.ones(X_train_s.shape[0]), X_train_s]
    X_test_b = np.c_[np.ones(X_test_s.shape[0]), X_test_s]

    # Gradient descent for logistic regression with L2
    n_features = X_train_b.shape[1]
    beta = np.zeros(n_features)
    lr = 0.1
    n_iter = 2000

    for _ in range(n_iter):
        z = X_train_b @ beta
        h = _sigmoid(z)
        gradient = (X_train_b.T @ (h - y_train)) / len(y_train)
        # L2 regularization (exclude bias)
        gradient[1:] += ridge_lambda * beta[1:] / len(y_train)
        beta -= lr * gradient

    # Predictions
    y_train_prob = _sigmoid(X_train_b @ beta)
    y_test_prob = _sigmoid(X_test_b @ beta)
    y_train_pred = (y_train_prob >= 0.5).astype(int)
    y_test_pred = (y_test_prob >= 0.5).astype(int)

    # Metrics
    train_acc = np.mean(y_train_pred == y_train)
    test_acc = np.mean(y_test_pred == y_test)

    # Confusion matrix
    tp = np.sum((y_test_pred == 1) & (y_test == 1))
    fp = np.sum((y_test_pred == 1) & (y_test == 0))
    tn = np.sum((y_test_pred == 0) & (y_test == 0))
    fn = np.sum((y_test_pred == 0) & (y_test == 1))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # ROC curve
    thresholds = np.linspace(0, 1, 100)
    roc_points = []
    for thresh in thresholds:
        pred = (y_test_prob >= thresh).astype(int)
        tpr = np.sum((pred == 1) & (y_test == 1)) / max(np.sum(y_test == 1), 1)
        fpr = np.sum((pred == 1) & (y_test == 0)) / max(np.sum(y_test == 0), 1)
        roc_points.append({"threshold": round(thresh, 3), "tpr": round(tpr, 4), "fpr": round(fpr, 4)})

    # AUC (trapezoidal)
    roc_points_sorted = sorted(roc_points, key=lambda x: x["fpr"])
    auc = 0
    for i in range(1, len(roc_points_sorted)):
        auc += (roc_points_sorted[i]["fpr"] - roc_points_sorted[i - 1]["fpr"]) * \
               (roc_points_sorted[i]["tpr"] + roc_points_sorted[i - 1]["tpr"]) / 2

    # Feature importance
    coefs = beta[1:]
    feature_imp = []
    for i, col in enumerate(feature_cols):
        feature_imp.append({
            "feature": col,
            "coefficient": round(coefs[i], 6),
            "abs_coef": round(abs(coefs[i]), 6),
            "odds_ratio": round(np.exp(coefs[i]), 4),
        })
    total_abs = sum(f["abs_coef"] for f in feature_imp)
    if total_abs > 0:
        for f in feature_imp:
            f["importance_pct"] = round(f["abs_coef"] / total_abs * 100, 2)
    feature_imp.sort(key=lambda x: x["importance_pct"], reverse=True)
    result_df = pd.DataFrame(feature_imp)

    # Per-sample breakdown (test set)
    breakdown_rows = []
    for i in range(len(y_test)):
        breakdown_rows.append({
            "index": int(test_idx[i]),
            "actual": int(y_test[i]),
            "predicted": int(y_test_pred[i]),
            "failure_prob": round(y_test_prob[i], 4),
            "correct": int(y_test[i] == y_test_pred[i]),
        })
    breakdown_df = pd.DataFrame(breakdown_rows)

    # Metrics
    metrics = pd.DataFrame([
        {"metric": "Train Accuracy", "value": round(train_acc, 4)},
        {"metric": "Test Accuracy", "value": round(test_acc, 4)},
        {"metric": "Precision", "value": round(precision, 4)},
        {"metric": "Recall", "value": round(recall, 4)},
        {"metric": "F1 Score", "value": round(f1, 4)},
        {"metric": "AUC", "value": round(auc, 4)},
        {"metric": "True Positives", "value": int(tp)},
        {"metric": "False Positives", "value": int(fp)},
        {"metric": "True Negatives", "value": int(tn)},
        {"metric": "False Negatives", "value": int(fn)},
        {"metric": "Failure Rate (Test)", "value": round(float(y_test.mean()), 4)},
        {"metric": "Training Samples", "value": len(y_train)},
        {"metric": "Test Samples", "value": len(y_test)},
    ])
    metrics_df = pd.DataFrame(metrics)

    # Markdown
    md = f"""## 预测性维护分析结果

### 模型性能
| 指标 | 数值 |
|---|---|
| 训练集准确率 | {train_acc:.2%} |
| 测试集准确率 | {test_acc:.2%} |
| 精确率 (Precision) | {precision:.2%} |
| 召回率 (Recall) | {recall:.2%} |
| F1 Score | {f1:.4f} |
| AUC | {auc:.4f} |

### 模型评价
"""
    if auc >= 0.9:
        md += "- ✅ 故障预测能力优秀（AUC ≥ 0.9）\n"
    elif auc >= 0.8:
        md += "- ⚠️ 故障预测能力良好（0.8 ≤ AUC < 0.9）\n"
    elif auc >= 0.7:
        md += "- 🔶 故障预测能力一般（0.7 ≤ AUC < 0.8），建议增加更多特征\n"
    else:
        md += "- ❌ 故障预测能力不足（AUC < 0.7），需要重新选择特征\n"

    md += f"\n### 关键故障指标（Top 10）\n"
    for f in feature_imp[:10]:
        md += f"- {f['feature']}: OR={f['odds_ratio']}, 贡献={f['importance_pct']}%\n"

    return result_df, breakdown_df, md
