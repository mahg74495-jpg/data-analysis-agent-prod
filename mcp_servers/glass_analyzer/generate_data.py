#!/usr/bin/env python3
"""
玻璃性能测试 - 模拟数据生成器
生成4000个点位×4个站点的测试数据
"""
import numpy as np
import pandas as pd
import os, json
from pathlib import Path

DATA_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "data"
OUTPUT_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "output"

def generate_panel(panel_id: int, grid_h: int = 80, grid_w: int = 50, seed: int = None):
    """
    模拟一片玻璃在4个站点的测试数据
    
    参数:
        panel_id: 玻璃编号
        grid_h, grid_w: 点位网格 (80×50=4000点)
        seed: 随机种子
    
    返回:
        dict: {station: (h, w) 数组}
    """
    if seed is None:
        seed = panel_id
    rng = np.random.RandomState(seed)
    
    # === 真实值（玻璃本身的性能分布）===
    # 用二维高斯混合模拟真实的性能分布（有高有低）
    x = np.linspace(-2, 2, grid_w)
    y = np.linspace(-2, 2, grid_h)
    xx, yy = np.meshgrid(x, y)
    
    # 真实值 = 中心峰 + 边缘渐变 + 随机纹理
    true_value = (
        100.0  # 基准值
        + 5.0 * np.exp(-0.5 * (xx**2 + yy**2))  # 中心凸起
        + 2.0 * np.sin(xx * 1.5) * np.cos(yy * 1.2)  # 波浪纹理
        + 1.5 * np.sin(xx * 3.0 + yy * 2.0)  # 精细纹理
    )
    
    # === 站点偏差（每个站点有系统性的测量偏差）===
    station_bias = {
        "A": 0.0,      # 基准站，无偏差
        "B": -1.5,     # 偏低1.5
        "C": +2.0,     # 偏高2.0
        "D": +0.8,     # 偏高0.8
    }
    
    # === 站点噪声（每个站点测量精度不同）===
    station_noise_std = {
        "A": 0.3,
        "B": 0.5,
        "C": 0.4,
        "D": 0.6,
    }
    
    # === 站点空间漂移（某些站点有边缘效应）===
    def edge_effect(h, w, strength=0.5):
        """边缘衰减效应"""
        edge_dist = np.minimum(
            np.minimum(np.arange(h)[:, None], np.arange(w)[None, :]),
            np.minimum(h - 1 - np.arange(h)[:, None], w - 1 - np.arange(w)[None, :])
        )
        return strength * np.exp(-edge_dist / 10.0)
    
    results = {}
    for station in ["A", "B", "C", "D"]:
        noise = rng.normal(0, station_noise_std[station], (grid_h, grid_w))
        edge = edge_effect(grid_h, grid_w, strength=0.3 if station in ["B", "D"] else 0.0)
        measured = true_value + station_bias[station] + noise + edge
        results[station] = measured
    
    return results, true_value


def generate_batch(num_panels: int = 10, grid_h: int = 80, grid_w: int = 50):
    """
    生成一批玻璃的测试数据，保存为Parquet
    
    每片玻璃：4000点 × 4站点 = 16000个数值
    每批10片：160000个数值（演示用）
    实际批次100K片：16亿点
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    
    all_records = []
    
    for pid in range(num_panels):
        results, true_val = generate_panel(pid, grid_h, grid_w)
        
        # 展平为记录格式
        for row in range(grid_h):
            for col in range(grid_w):
                point_id = row * grid_w + col
                record = {
                    "panel_id": pid,
                    "point_id": point_id,
                    "row": row,
                    "col": col,
                    "true_value": round(float(true_val[row, col]), 3),
                    "station_A": round(float(results["A"][row, col]), 3),
                    "station_B": round(float(results["B"][row, col]), 3),
                    "station_C": round(float(results["C"][row, col]), 3),
                    "station_D": round(float(results["D"][row, col]), 3),
                }
                all_records.append(record)
        
        if (pid + 1) % 10 == 0:
            print(f"  已生成 {pid+1}/{num_panels} 片")
    
    # 转DataFrame
    df = pd.DataFrame(all_records)
    
    # 保存为Parquet（列式压缩存储）
    parquet_path = DATA_DIR / f"glass_batch_{num_panels}panels_{grid_h}x{grid_w}.parquet"
    df.to_parquet(parquet_path, index=False)
    
    # 也保存一份CSV方便查看（仅前100行）
    csv_path = DATA_DIR / f"glass_batch_{num_panels}panels_{grid_h}x{grid_w}_sample.csv"
    df.head(100).to_csv(csv_path, index=False)
    
    file_size_mb = os.path.getsize(parquet_path) / 1024 / 1024
    
    print(f"\n✅ 数据生成完成!")
    print(f"   玻璃数: {num_panels}")
    print(f"   每片点数: {grid_h}×{grid_w} = {grid_h*grid_w}")
    print(f"   总记录数: {len(df):,}")
    print(f"   Parquet文件: {parquet_path}")
    print(f"   文件大小: {file_size_mb:.2f} MB")
    print(f"   每片数据量: {file_size_mb/num_panels*1000:.1f} KB/片")
    
    # 估算100K片的规模
    est_size_gb = file_size_mb / num_panels * 100000 / 1024
    print(f"\n📊 估算100K片规模:")
    print(f"   总记录数: {100000 * grid_h * grid_w:,} 条")
    print(f"   预估文件大小: {est_size_gb:.1f} GB")
    
    return df


if __name__ == "__main__":
    print("=" * 50)
    print("玻璃性能测试 - 模拟数据生成")
    print("=" * 50)
    
    # 生成10片玻璃的演示数据
    df = generate_batch(num_panels=10, grid_h=80, grid_w=50)
    
    print("\n数据预览:")
    print(df.head())
    print(f"\n数据统计:")
    print(df.describe())
