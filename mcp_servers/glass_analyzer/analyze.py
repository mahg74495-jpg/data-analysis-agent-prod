#!/usr/bin/env python3
"""
玻璃性能测试 - 四站点差异分析引擎
计算每个站点之间的差异，生成表征参数和可视化报告
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import seaborn as sns
import json, os, sys, argparse
from pathlib import Path
from scipy import stats

# 中文字体设置
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "Heiti SC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

DATA_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "data"
OUTPUT_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_data(parquet_path: str = None):
    """加载Parquet数据"""
    if parquet_path is None:
        # 自动找最新的
        files = sorted(DATA_DIR.glob("*.parquet"))
        if not files:
            print("❌ 未找到Parquet数据文件，请先运行 generate_data.py 或 import_data.py")
            sys.exit(1)
        parquet_path = str(files[-1])
    
    print(f"📂 加载数据: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    print(f"   记录数: {len(df):,}")
    print(f"   列: {list(df.columns)}")
    
    # 自动识别站点列
    station_cols = [c for c in df.columns if c.lower().startswith("station_")]
    if not station_cols:
        print("❌ 未找到站点列（station_A, station_B, ...），请先用 import_data.py 导入")
        sys.exit(1)
    print(f"   站点列: {station_cols}")
    
    return df


def compute_differences(df: pd.DataFrame):
    """
    计算四个站点两两之间的差异
    
    返回:
        diff_df: 每个点位的差异数据
        summary: 表征参数汇总
    """
    stations = ["station_A", "station_B", "station_C", "station_D"]
    station_pairs = [
        ("A", "B"), ("A", "C"), ("A", "D"),
        ("B", "C"), ("B", "D"), ("C", "D"),
    ]
    
    diff_df = df[["panel_id", "point_id", "row", "col"]].copy()
    
    for s1, s2 in station_pairs:
        col_a = f"station_{s1}"
        col_b = f"station_{s2}"
        diff_df[f"Δ{s1}{s2}"] = (df[col_a] - df[col_b]).round(3)
        diff_df[f"|Δ{s1}{s2}|"] = np.abs(diff_df[f"Δ{s1}{s2}"]).round(3)
    
    return diff_df


def compute_summary_params(diff_df: pd.DataFrame):
    """
    计算表征参数
    
    返回:
        summary: dict, 每个站点对的差异表征
    """
    station_pairs = ["AB", "AC", "AD", "BC", "BD", "CD"]
    
    summary = {}
    for pair in station_pairs:
        abs_col = f"|Δ{pair}|"
        raw_col = f"Δ{pair}"
        
        values = diff_df[abs_col].values
        raw_values = diff_df[raw_col].values
        
        summary[pair] = {
            # 核心表征参数
            "RMSE": round(np.sqrt(np.mean(raw_values ** 2)), 4),
            "MAE": round(np.mean(values), 4),           # 平均绝对差异
            "Max_Diff": round(np.max(values), 4),        # 最大差异
            "P95_Diff": round(np.percentile(values, 95), 4),  # 95%分位差异
            "Median_Diff": round(np.median(values), 4),  # 中位数差异
            "Std_Diff": round(np.std(values), 4),        # 差异标准差
            
            # 偏差方向
            "Mean_Bias": round(np.mean(raw_values), 4),  # 平均偏差（有正负）
            "Bias_Direction": "A偏高" if np.mean(raw_values) > 0 else "B偏高",
            
            # 分布特征
            "Skewness": round(stats.skew(values), 4),    # 偏度
            "Kurtosis": round(stats.kurtosis(values), 4), # 峰度
        }
    
    return summary


def compute_panel_summary(diff_df: pd.DataFrame):
    """每片玻璃的差异汇总"""
    station_pairs = ["AB", "AC", "AD", "BC", "BD", "CD"]
    
    panel_stats = []
    for pid in diff_df["panel_id"].unique():
        panel_data = diff_df[diff_df["panel_id"] == pid]
        row = {"panel_id": pid}
        for pair in station_pairs:
            abs_col = f"|Δ{pair}|"
            row[f"RMSE_{pair}"] = round(np.sqrt(np.mean(panel_data[f"Δ{pair}"].values ** 2)), 4)
            row[f"MAE_{pair}"] = round(np.mean(panel_data[abs_col].values), 4)
            row[f"P95_{pair}"] = round(np.percentile(panel_data[abs_col].values, 95), 4)
        panel_stats.append(row)
    
    return pd.DataFrame(panel_stats)


def plot_heatmap_comparison(diff_df: pd.DataFrame, panel_id: int = 0, grid_h: int = 80, grid_w: int = 50):
    """绘制某片玻璃的差异热力图"""
    panel_diff = diff_df[diff_df["panel_id"] == panel_id]
    
    station_pairs = ["AB", "AC", "AD", "BC", "BD", "CD"]
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle(f"玻璃 #{panel_id} — 四站点差异热力图", fontsize=16, fontweight="bold")
    
    vmax = 0
    for pair in station_pairs:
        abs_col = f"|Δ{pair}|"
        vmax = max(vmax, panel_diff[abs_col].max())
    
    for idx, pair in enumerate(station_pairs):
        ax = axes[idx // 3][idx % 3]
        abs_col = f"|Δ{pair}|"
        
        heatmap = panel_diff.pivot_table(index="row", columns="col", values=abs_col)
        im = ax.imshow(heatmap.values, cmap="YlOrRd", vmin=0, vmax=vmax, aspect="auto")
        ax.set_title(f"站点 {pair[0]} vs {pair[1]}", fontsize=12)
        ax.set_xlabel("列")
        ax.set_ylabel("行")
        plt.colorbar(im, ax=ax, shrink=0.8)
    
    plt.tight_layout()
    save_path = OUTPUT_DIR / f"heatmap_panel{panel_id}.png"
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  热力图已保存: {save_path}")
    return str(save_path)


def plot_distribution(diff_df: pd.DataFrame):
    """绘制差异分布图"""
    station_pairs = ["AB", "AC", "AD", "BC", "BD", "CD"]
    
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle("四站点差异分布（所有玻璃汇总）", fontsize=16, fontweight="bold")
    
    for idx, pair in enumerate(station_pairs):
        ax = axes[idx // 3][idx % 3]
        abs_col = f"|Δ{pair}|"
        values = diff_df[abs_col].values
        
        ax.hist(values, bins=80, alpha=0.7, color="steelblue", edgecolor="white", linewidth=0.3)
        ax.axvline(np.mean(values), color="red", linestyle="--", label=f"均值={np.mean(values):.3f}")
        ax.axvline(np.percentile(values, 95), color="orange", linestyle="--", label=f"P95={np.percentile(values, 95):.3f}")
        ax.set_title(f"站点 {pair[0]} vs {pair[1]}", fontsize=12)
        ax.set_xlabel("绝对差异")
        ax.set_ylabel("频次")
        ax.legend(fontsize=8)
    
    plt.tight_layout()
    save_path = OUTPUT_DIR / "distribution_all.png"
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  分布图已保存: {save_path}")
    return str(save_path)


def plot_panel_comparison(panel_summary: pd.DataFrame):
    """每片玻璃的差异对比"""
    fig, axes = plt.subplots(2, 1, figsize=(14, 10))
    fig.suptitle("每片玻璃 — 四站点差异对比", fontsize=16, fontweight="bold")
    
    # RMSE对比
    ax = axes[0]
    pairs = ["AB", "AC", "AD", "BC", "BD", "CD"]
    x = np.arange(len(panel_summary))
    width = 0.12
    
    for i, pair in enumerate(pairs):
        ax.bar(x + i * width, panel_summary[f"RMSE_{pair}"], width, label=f"RMSE_{pair}")
    ax.set_xlabel("玻璃编号")
    ax.set_ylabel("RMSE")
    ax.set_xticks(x + width * 2.5)
    ax.set_xticklabels(panel_summary["panel_id"])
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    
    # MAE对比
    ax = axes[1]
    for i, pair in enumerate(pairs):
        ax.bar(x + i * width, panel_summary[f"MAE_{pair}"], width, label=f"MAE_{pair}")
    ax.set_xlabel("玻璃编号")
    ax.set_ylabel("MAE")
    ax.set_xticks(x + width * 2.5)
    ax.set_xticklabels(panel_summary["panel_id"])
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    
    plt.tight_layout()
    save_path = OUTPUT_DIR / "panel_comparison.png"
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  玻璃对比图已保存: {save_path}")
    return str(save_path)


def plot_spatial_error(diff_df: pd.DataFrame, grid_h: int = 80, grid_w: int = 50):
    """所有玻璃平均后的空间差异分布（看系统性的位置偏差）"""
    station_pairs = ["AB", "AC", "AD", "BC", "BD", "CD"]
    
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle("空间差异分布（所有玻璃平均）", fontsize=16, fontweight="bold")
    
    for idx, pair in enumerate(station_pairs):
        ax = axes[idx // 3][idx % 3]
        abs_col = f"|Δ{pair}|"
        
        # 按row,col分组求均值
        spatial_mean = diff_df.groupby(["row", "col"])[abs_col].mean().reset_index()
        heatmap = spatial_mean.pivot_table(index="row", columns="col", values=abs_col)
        
        im = ax.imshow(heatmap.values, cmap="YlOrRd", aspect="auto")
        ax.set_title(f"站点 {pair[0]} vs {pair[1]}", fontsize=12)
        ax.set_xlabel("列")
        ax.set_ylabel("行")
        plt.colorbar(im, ax=ax, shrink=0.8)
    
    plt.tight_layout()
    save_path = OUTPUT_DIR / "spatial_error.png"
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  空间误差图已保存: {save_path}")
    return str(save_path)


def generate_report(summary: dict, panel_summary: pd.DataFrame, diff_df: pd.DataFrame, image_paths: list):
    """生成JSON报告"""
    report = {
        "报告信息": {
            "生成时间": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "玻璃数": int(diff_df["panel_id"].nunique()),
            "每片点数": int(len(diff_df) / diff_df["panel_id"].nunique()),
            "站点": ["A", "B", "C", "D"],
        },
        "差异表征参数": {},
        "玻璃级统计": {},
        "可视化文件": image_paths,
    }
    
    # 整理表征参数
    for pair, params in summary.items():
        report["差异表征参数"][f"站点{pair[0]}vs{pair[1]}"] = {
            "RMSE": params["RMSE"],
            "MAE": params["MAE"],
            "最大差异": params["Max_Diff"],
            "P95差异": params["P95_Diff"],
            "中位数差异": params["Median_Diff"],
            "标准差": params["Std_Diff"],
            "平均偏差": params["Mean_Bias"],
            "偏差方向": params["Bias_Direction"],
        }
    
    # 每片玻璃的统计
    for _, row in panel_summary.iterrows():
        pid = int(row["panel_id"])
        report["玻璃级统计"][f"玻璃#{pid}"] = {
            f"RMSE_{pair}": round(row[f"RMSE_{pair}"], 4)
            for pair in ["AB", "AC", "AD", "BC", "BD", "CD"]
        }
    
    # 保存JSON
    json_path = OUTPUT_DIR / "analysis_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  JSON报告已保存: {json_path}")
    
    return report


def print_console_report(summary: dict):
    """控制台打印简洁报告"""
    print("\n" + "=" * 60)
    print("📊 四站点差异分析报告")
    print("=" * 60)
    
    print(f"\n{'站点对':<10} {'RMSE':<10} {'MAE':<10} {'P95':<10} {'最大差异':<10} {'平均偏差':<10}")
    print("-" * 60)
    for pair, params in summary.items():
        print(f"{pair:<10} {params['RMSE']:<10.4f} {params['MAE']:<10.4f} "
              f"{params['P95_Diff']:<10.4f} {params['Max_Diff']:<10.4f} "
              f"{params['Mean_Bias']:<10.4f}")
    
    print("\n📌 解读:")
    print(f"  - RMSE越小 → 两站点一致性越好")
    print(f"  - P95差异 < 1.0 → 95%的点位差异在1.0以内")
    print(f"  - 平均偏差接近0 → 无系统性偏差")
    print(f"  - 平均偏差偏离0 → 存在系统偏差，需校准")


def main():
    parser = argparse.ArgumentParser(description="玻璃四站点差异分析引擎")
    parser.add_argument("--file", help="指定Parquet文件路径（默认自动找最新的）")
    parser.add_argument("--panel", type=int, default=0, help="热力图显示的玻璃编号（默认: 0）")
    args = parser.parse_args()
    
    print("=" * 60)
    print("玻璃性能测试 - 四站点差异分析引擎")
    print("=" * 60)
    
    # 1. 加载数据
    df = load_data(args.file)
    
    # 2. 计算差异
    print("\n🔬 计算四站点差异...")
    diff_df = compute_differences(df)
    print(f"   差异数据: {len(diff_df):,} 行 × {len(diff_df.columns)} 列")
    
    # 3. 计算表征参数
    print("\n📐 计算表征参数...")
    summary = compute_summary_params(diff_df)
    print_console_report(summary)
    
    # 4. 每片玻璃的差异汇总
    print("\n📋 计算每片玻璃差异...")
    panel_summary = compute_panel_summary(diff_df)
    print(panel_summary.to_string(index=False))
    
    # 5. 可视化
    print("\n🎨 生成可视化图表...")
    image_paths = []
    image_paths.append(plot_heatmap_comparison(diff_df, panel_id=args.panel))
    image_paths.append(plot_distribution(diff_df))
    image_paths.append(plot_panel_comparison(panel_summary))
    image_paths.append(plot_spatial_error(diff_df))
    
    # 6. 生成报告
    print("\n📝 生成报告...")
    report = generate_report(summary, panel_summary, diff_df, image_paths)
    
    print("\n" + "=" * 60)
    print(f"✅ 分析完成！所有文件在: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
