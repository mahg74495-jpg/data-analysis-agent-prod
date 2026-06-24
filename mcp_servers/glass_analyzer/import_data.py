#!/usr/bin/env python3
"""
玻璃测试数据导入适配器
支持多种设备输出格式 → 统一Parquet格式

使用方式:
  python3 import_data.py --help
  python3 import_data.py --dir ./原始数据/ --format csv
  python3 import_data.py --dir ./原始数据/ --format csv --station_col 站点 --value_col 数值
"""
import pandas as pd
import numpy as np
import argparse, json, os, sys, glob
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def detect_format(file_path: str) -> str:
    """自动检测文件格式"""
    ext = Path(file_path).suffix.lower()
    if ext == ".csv":
        return "csv"
    elif ext in (".xls", ".xlsx"):
        return "excel"
    elif ext == ".txt":
        return "txt"
    elif ext == ".parquet":
        return "parquet"
    return "unknown"


def auto_detect_columns(df: pd.DataFrame) -> dict:
    """
    自动猜测列含义
    返回: {"panel_id": "列名", "point_id": "列名", "row": "列名", "col": "列名", "value": "列名", "station": "列名"}
    """
    cols_lower = {c: c.lower() for c in df.columns}
    rev_map = {v: k for k, v in cols_lower.items()}
    
    result = {}
    
    # panel_id: 包含 panel/玻璃/批次/片号/glass/batch/lot
    for keyword in ["panel", "玻璃", "片号", "批次", "glass", "batch", "lot", "产品", "product"]:
        for c, cl in cols_lower.items():
            if keyword in cl:
                result["panel_id"] = c
                break
        if "panel_id" in result:
            break
    
    # point_id: 包含 point/点/序号/point_id/编号
    for keyword in ["point_id", "point", "点位", "序号", "编号", "id", "index", "pixel", "像素"]:
        for c, cl in cols_lower.items():
            if keyword in cl and c not in result.values():
                result["point_id"] = c
                break
        if "point_id" in result:
            break
    
    # row/col: 包含 row/行/列/col/x/y/坐标
    for keyword in ["row", "行", "r"]:
        for c, cl in cols_lower.items():
            if cl == keyword and c not in result.values():
                result["row"] = c
                break
        if "row" in result:
            break
    
    for keyword in ["col", "列", "c", "column"]:
        for c, cl in cols_lower.items():
            if cl == keyword and c not in result.values():
                result["col"] = c
                break
        if "col" in result:
            break
    
    # x/y 坐标
    for keyword in ["x", "x坐标", "x_coord"]:
        for c, cl in cols_lower.items():
            if cl == keyword and c not in result.values():
                result["x"] = c
                break
        if "x" in result:
            break
    
    for keyword in ["y", "y坐标", "y_coord"]:
        for c, cl in cols_lower.items():
            if cl == keyword and c not in result.values():
                result["y"] = c
                break
        if "y" in result:
            break
    
    # station: 包含 station/站点/站/工位/测试站
    for keyword in ["station", "站点", "工位", "测试站", "站", "site"]:
        for c, cl in cols_lower.items():
            if keyword in cl and c not in result.values():
                result["station"] = c
                break
        if "station" in result:
            break
    
    # value: 包含 value/值/数值/测量/结果/result/measure/测试值/thickness/厚度
    for keyword in ["value", "值", "数值", "测量", "结果", "result", "measure", "测试值", "thickness", "厚度", "性能", "performance"]:
        for c, cl in cols_lower.items():
            if keyword in cl and c not in result.values():
                result["value"] = c
                break
        if "value" in result:
            break
    
    return result


def import_from_csv(csv_path: str, col_mapping: dict = None, station_name: str = None) -> pd.DataFrame:
    """
    从CSV导入单站点数据
    
    参数:
        csv_path: CSV文件路径
        col_mapping: 列映射 {标准列名: 实际列名}
        station_name: 站点名称（如"A"），如果CSV中不包含站点列
    """
    df = pd.read_csv(csv_path)
    
    # 自动检测列
    if col_mapping is None:
        col_mapping = auto_detect_columns(df)
    
    print(f"  检测到的列映射: {col_mapping}")
    
    # 重命名标准列
    rename = {}
    for std_col, actual_col in col_mapping.items():
        if actual_col in df.columns:
            rename[actual_col] = std_col
    
    df = df.rename(columns=rename)
    
    # 确保有panel_id
    if "panel_id" not in df.columns:
        df["panel_id"] = 0  # 默认编号
    
    # 确保有point_id
    if "point_id" not in df.columns:
        if "row" in df.columns and "col" in df.columns:
            df["point_id"] = df["row"] * df["col"].max() + df["col"]
        else:
            df["point_id"] = df.index
    
    # 确保有row/col（从point_id推算）
    if "row" not in df.columns and "col" not in df.columns:
        n_points = len(df)
        grid_w = int(np.sqrt(n_points))
        grid_h = n_points // grid_w
        while grid_w * grid_h < n_points:
            grid_w += 1
        df["row"] = df["point_id"] // grid_w
        df["col"] = df["point_id"] % grid_w
    
    # 站点名
    if station_name:
        df["station"] = station_name
    
    return df


def import_multi_station(dir_path: str, file_pattern: str = "*.csv", 
                          station_map: dict = None, col_mapping: dict = None):
    """
    从目录导入多站点数据（每个站点一个文件）
    
    参数:
        dir_path: 数据目录
        file_pattern: 文件匹配模式
        station_map: 文件名→站点名映射，如 {"site1.csv": "A", "site2.csv": "B"}
                      不传则按文件顺序自动分配 A/B/C/D
        col_mapping: 列映射
    """
    files = sorted(glob.glob(os.path.join(dir_path, file_pattern)))
    if not files:
        print(f"❌ 未找到匹配 {file_pattern} 的文件")
        return None
    
    print(f"📂 找到 {len(files)} 个文件:")
    for f in files:
        print(f"   - {f}")
    
    if station_map is None:
        # 自动分配站点名
        stations = ["A", "B", "C", "D"]
        station_map = {os.path.basename(f): stations[i] if i < len(stations) else f"站{i+1}" 
                       for i, f in enumerate(files)}
    
    all_dfs = []
    for file_path in files:
        fname = os.path.basename(file_path)
        station = station_map.get(fname, "未知")
        print(f"\n  导入 {fname} → 站点 {station}")
        
        fmt = detect_format(file_path)
        if fmt == "csv":
            df = import_from_csv(file_path, col_mapping, station_name=station)
        elif fmt == "excel":
            df = pd.read_excel(file_path)
            if col_mapping:
                df = import_from_csv.__wrapped__(file_path, col_mapping, station_name=station)
            else:
                cm = auto_detect_columns(df)
                df = df.rename(columns={v: k for k, v in cm.items() if v in df.columns})
                df["station"] = station
        else:
            print(f"  ⚠️ 不支持格式: {fmt}")
            continue
        
        all_dfs.append(df)
    
    if not all_dfs:
        return None
    
    # 合并所有站点
    combined = pd.concat(all_dfs, ignore_index=True)
    
    # 透视：每个点位的多站点值转成宽表
    pivot = combined.pivot_table(
        index=["panel_id", "point_id", "row", "col"],
        columns="station",
        values="value",
        aggfunc="first"
    ).reset_index()
    
    # 重命名站点列为 station_A, station_B, ...
    pivot.columns = [f"station_{c}" if c in ["A","B","C","D"] else c 
                     for c in pivot.columns]
    
    return pivot


def import_single_file(file_path: str, col_mapping: dict = None):
    """
    从单个文件导入（所有站点数据在一个文件中）
    
    支持格式:
      - 宽表: panel_id, point_id, row, col, station_A, station_B, station_C, station_D
      - 长表: panel_id, point_id, row, col, station, value
    """
    fmt = detect_format(file_path)
    print(f"📂 导入文件: {file_path} (格式: {fmt})")
    
    if fmt == "csv":
        df = pd.read_csv(file_path)
    elif fmt == "excel":
        df = pd.read_excel(file_path)
    elif fmt == "parquet":
        df = pd.read_parquet(file_path)
    else:
        print(f"❌ 不支持格式: {fmt}")
        return None
    
    print(f"   列: {list(df.columns)}")
    print(f"   行数: {len(df):,}")
    
    # 检测是否已经是宽表格式（包含 station_A 等列）
    station_cols = [c for c in df.columns if c.lower().startswith("station_")]
    
    if station_cols:
        print(f"   检测到宽表格式，站点列: {station_cols}")
        return df
    
    # 检测是否长表格式（包含 station 和 value 列）
    if col_mapping is None:
        col_mapping = auto_detect_columns(df)
    
    if "station" in col_mapping and "value" in col_mapping:
        print(f"   检测到长表格式，透视中...")
        rename = {v: k for k, v in col_mapping.items() if v in df.columns}
        df = df.rename(columns=rename)
        
        pivot = df.pivot_table(
            index=["panel_id", "point_id", "row", "col"],
            columns="station",
            values="value",
            aggfunc="first"
        ).reset_index()
        
        pivot.columns = [f"station_{c}" if c in ["A","B","C","D"] else c 
                         for c in pivot.columns]
        return pivot
    
    print(f"⚠️ 无法自动识别格式，请使用 --col_mapping 指定列映射")
    return None


def save_to_parquet(df: pd.DataFrame, output_name: str = "imported_data"):
    """保存为Parquet"""
    os.makedirs(DATA_DIR, exist_ok=True)
    output_path = DATA_DIR / f"{output_name}.parquet"
    df.to_parquet(output_path, index=False)
    file_size = os.path.getsize(output_path) / 1024 / 1024
    print(f"\n✅ 已保存: {output_path} ({file_size:.2f} MB)")
    print(f"   记录数: {len(df):,}")
    print(f"   列: {list(df.columns)}")
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(description="玻璃测试数据导入适配器")
    parser.add_argument("--dir", help="数据目录（多文件模式，每个站点一个文件）")
    parser.add_argument("--file", help="单个数据文件（所有站点在一个文件中）")
    parser.add_argument("--pattern", default="*.csv", help="文件匹配模式（默认: *.csv）")
    parser.add_argument("--format", choices=["csv", "excel", "parquet"], default="csv", help="文件格式")
    parser.add_argument("--station_col", help="站点列名（长表格式）")
    parser.add_argument("--value_col", help="数值列名（长表格式）")
    parser.add_argument("--panel_col", help="玻璃编号列名")
    parser.add_argument("--point_col", help="点位编号列名")
    parser.add_argument("--row_col", help="行坐标列名")
    parser.add_argument("--col_col", help="列坐标列名")
    parser.add_argument("--output", default="imported_data", help="输出文件名（不含扩展名）")
    parser.add_argument("--station_map", help="文件名→站点映射JSON，如 '{\"a.csv\":\"A\",\"b.csv\":\"B\"}'")
    
    args = parser.parse_args()
    
    # 构建列映射
    col_mapping = {}
    if args.panel_col: col_mapping["panel_id"] = args.panel_col
    if args.point_col: col_mapping["point_id"] = args.point_col
    if args.row_col: col_mapping["row"] = args.row_col
    if args.col_col: col_mapping["col"] = args.col_col
    if args.station_col: col_mapping["station"] = args.station_col
    if args.value_col: col_mapping["value"] = args.value_col
    if not col_mapping:
        col_mapping = None  # 自动检测
    
    # 站点映射
    station_map = None
    if args.station_map:
        station_map = json.loads(args.station_map)
    
    # 执行导入
    if args.dir:
        df = import_multi_station(args.dir, args.pattern, station_map, col_mapping)
    elif args.file:
        df = import_single_file(args.file, col_mapping)
    else:
        parser.print_help()
        print("\n⚠️ 请指定 --dir 或 --file")
        return
    
    if df is not None:
        save_to_parquet(df, args.output)
        print("\n💡 然后运行: python3 analyze.py")
        print(f"   会自动加载 data/{args.output}.parquet")


if __name__ == "__main__":
    main()
