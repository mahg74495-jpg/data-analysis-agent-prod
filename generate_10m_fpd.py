#!/usr/bin/env python3
"""生成1000万行平板显示行业良率数据 → SQLite"""
import sqlite3
import numpy as np
import os
import time
from datetime import datetime, timedelta

DB_PATH = "/Users/viton/Data-Analysis-Agent/data/fpd_yield_10m.db"
CSV_PATH = "/Users/viton/Data-Analysis-Agent/uploads/平板显示良率_1000万.csv"

# 平板显示行业参数
FACTORIES = ["G6阵列厂", "G8.5阵列厂", "G10.5阵列厂", "CF彩膜厂", "Cell成盒厂", "Module模组厂"]
PROCESSES = ["TFT光刻", "TFT刻蚀", "CF涂布", "CF曝光", "Cell贴合", "Cell切割",
             "Module绑定", "Module组装", "OLED蒸镀", "OLED封装"]
PRODUCTS = ["55\"TV面板", "65\"TV面板", "75\"TV面板", "6.1\"手机OLED", "6.7\"手机OLED",
            "10.9\"平板LCD", "12.9\"平板LCD", "15.4\"车载面板", "27\"显示器面板", "32\"显示器面板"]

START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2026, 6, 1)
DAYS = (END_DATE - START_DATE).days  # 517 days

TOTAL_ROWS = 10_000_000
CHUNK_SIZE = 200_000  # 每批写入行数

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)

# 删除旧文件
for p in [DB_PATH, CSV_PATH]:
    if os.path.exists(p):
        os.remove(p)

print(f"目标: {TOTAL_ROWS:,} 行")
print(f"日期范围: {START_DATE.date()} ~ {END_DATE.date()} ({DAYS}天)")
print("="*60)

t0 = time.time()

# 建立SQLite
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("PRAGMA journal_mode=WAL")
cur.execute("PRAGMA synchronous=OFF")
cur.execute("""
CREATE TABLE fpd_yield (
    日期 TEXT,
    工厂 TEXT,
    制程 TEXT,
    产品 TEXT,
    投入基板数 INTEGER,
    良品基板数 INTEGER,
    不良数 INTEGER,
    良率_pct REAL,
    曝光剂量_mJ REAL,
    焦点偏移_um REAL,
    腔体压力_Torr REAL,
    RF功率_W REAL,
    研磨时间_s REAL,
    清洗液浓度_pct REAL,
    颗粒污染数 INTEGER,
    图案缺陷数 INTEGER,
    套刻偏移数 INTEGER,
    膜厚不均数 INTEGER,
    蚀刻残留数 INTEGER,
    划伤数 INTEGER
)
""")

# 预先分配产线-制程-产品组合 (减少每行随机开销)
combos = []
for f in FACTORIES:
    for p in PROCESSES:
        for pr in PRODUCTS:
            combos.append((f, p, pr))
print(f"产线×制程×产品组合: {len(combos)} 种")

# 每个组合的良率基准（不同组合良率不同）
np.random.seed(42)
base_yields = {c: np.random.uniform(88, 98) for c in combos}
# OLED产品良率偏低
for c in combos:
    if "OLED" in c[2]:
        base_yields[c] = np.random.uniform(75, 88)
    elif "车载" in c[2]:
        base_yields[c] = np.random.uniform(85, 95)
# G10.5产线良率略低（大尺寸更难）
for c in combos:
    if "G10.5" in c[0]:
        base_yields[c] -= np.random.uniform(1, 4)

# 设备参数基准（按制程不同）
process_params = {
    "TFT光刻": {"曝光剂量_mJ": (40, 60), "焦点偏移_um": (-0.05, 0.03), "腔体压力_Torr": (0.1, 0.5)},
    "TFT刻蚀": {"RF功率_W": (200, 500), "腔体压力_Torr": (0.05, 0.3)},
    "CF涂布": {"清洗液浓度_pct": (1, 5), "研磨时间_s": (30, 90)},
    "CF曝光": {"曝光剂量_mJ": (35, 55), "焦点偏移_um": (-0.04, 0.04)},
    "Cell贴合": {"腔体压力_Torr": (0.3, 0.8), "研磨时间_s": (60, 120)},
    "Cell切割": {"RF功率_W": (300, 600), "研磨时间_s": (40, 100)},
    "Module绑定": {"RF功率_W": (150, 350), "清洗液浓度_pct": (1, 4)},
    "Module组装": {"研磨时间_s": (20, 60), "清洗液浓度_pct": (1, 3)},
    "OLED蒸镀": {"曝光剂量_mJ": (50, 80), "腔体压力_Torr": (0.001, 0.01)},
    "OLED封装": {"RF功率_W": (250, 550), "研磨时间_s": (50, 110)},
}

# 开始生成（分批写入CSV）
rows_written = 0
csv_f = open(CSV_PATH, "w", encoding="utf-8-sig")
header = "日期,工厂,制程,产品,投入基板数,良品基板数,不良数,良率(%),曝光剂量(mJ),焦点偏移(μm),腔体压力(Torr),RF功率(W),研磨时间(s),清洗液浓度(%),颗粒污染数,图案缺陷数,套刻偏移数,膜厚不均数,蚀刻残留数,划伤数\n"
csv_f.write(header)

# 预生成日期序列
dates = [START_DATE + timedelta(days=d) for d in range(DAYS)]

batch_buffer = []
for i in range(TOTAL_ROWS):
    # 随机选组合
    idx = np.random.randint(0, len(combos))
    f, p, pr = combos[idx]
    
    # 日期
    dt = dates[np.random.randint(0, DAYS)]
    date_str = dt.strftime("%Y-%m-%d")
    
    # 良率计算（带波动和趋势）
    base = base_yields[(f, p, pr)]
    # 日波动 ±3%
    daily_fluctuation = np.random.normal(0, 3)
    # 时间趋势（2025下半年良率提升）
    days_from_start = (dt - START_DATE).days
    trend = min(days_from_start / 150 * 1.5, 5)  # 最多提升5个百分点
    yield_pct = np.clip(base + daily_fluctuation + trend, 50, 99.99)
    yield_pct = round(yield_pct, 2)
    
    # 投入基板数（大世代线更多）
    base_input = {"G6阵列厂": 300, "G8.5阵列厂": 500, "G10.5阵列厂": 400,
                  "CF彩膜厂": 450, "Cell成盒厂": 380, "Module模组厂": 600}.get(f, 400)
    input_count = int(np.random.poisson(base_input))
    input_count = max(50, input_count)
    
    # 良品和不良
    good = int(round(input_count * yield_pct / 100))
    bad = input_count - good
    
    # 设备参数
    params = process_params.get(p, {"曝光剂量_mJ": (30, 60), "焦点偏移_um": (-0.03, 0.03),
                                      "腔体压力_Torr": (0.1, 0.5), "RF功率_W": (200, 400),
                                      "研磨时间_s": (30, 100), "清洗液浓度_pct": (1, 5)})
    
    exposure = round(np.random.normal(np.mean(params.get("曝光剂量_mJ", (40, 60))),
                                      abs(params.get("曝光剂量_mJ", (40, 60))[1] - params.get("曝光剂量_mJ", (40, 60))[0])/6), 2)
    focus = round(np.random.normal(np.mean(params.get("焦点偏移_um", (-0.03, 0.03))),
                                   0.02), 4)
    pressure = round(abs(np.random.normal(np.mean(params.get("腔体压力_Torr", (0.1, 0.5))),
                                          0.1)), 4)
    rf_power = round(np.random.normal(np.mean(params.get("RF功率_W", (200, 400))), 50), 1)
    grind_time = round(np.random.normal(np.mean(params.get("研磨时间_s", (30, 100))), 20), 1)
    clean_conc = round(np.random.normal(np.mean(params.get("清洗液浓度_pct", (1, 5))), 1), 2)
    
    # 缺陷数（良率越低缺陷越多）
    defect_factor = max(0.5, (100 - yield_pct) / 10)
    particles = max(0, int(np.random.poisson(defect_factor * 5)))
    patterns = max(0, int(np.random.poisson(defect_factor * 2)))
    overlay = max(0, int(np.random.poisson(defect_factor * 1.5)))
    thickness = max(0, int(np.random.poisson(defect_factor * 1)))
    etch_res = max(0, int(np.random.poisson(defect_factor * 0.8)))
    scratch = max(0, int(np.random.poisson(defect_factor * 0.5)))
    
    row = f"{date_str},{f},{p},{pr},{input_count},{good},{bad},{yield_pct},{exposure},{focus},{pressure},{rf_power},{grind_time},{clean_conc},{particles},{patterns},{overlay},{thickness},{etch_res},{scratch}\n"
    batch_buffer.append(row)
    
    if len(batch_buffer) >= CHUNK_SIZE:
        csv_f.writelines(batch_buffer)
        rows_written += len(batch_buffer)
        elapsed = time.time() - t0
        pct = rows_written / TOTAL_ROWS * 100
        eta = elapsed / rows_written * (TOTAL_ROWS - rows_written) if rows_written > 0 else 0
        print(f"  [{pct:.1f}%] {rows_written:,}/{TOTAL_ROWS:,} | {elapsed:.0f}s | ETA {eta:.0f}s")
        batch_buffer = []

# 写入剩余
if batch_buffer:
    csv_f.writelines(batch_buffer)
    rows_written += len(batch_buffer)

csv_f.close()
elapsed = time.time() - t0
print(f"\n✅ CSV生成完成: {rows_written:,} 行 | 耗时 {elapsed:.0f}s")
csv_size = os.path.getsize(CSV_PATH) / 1024 / 1024
print(f"   文件大小: {csv_size:.0f} MB")

# 导入SQLite
print("\n📥 导入SQLite...")
t1 = time.time()
cur.execute("""
INSERT INTO fpd_yield 
SELECT * FROM read_csv_auto('{}', header=true)
""".format(CSV_PATH))
conn.commit()
sqlite_time = time.time() - t1

# 创建索引
print("📊 创建索引...")
cur.execute("CREATE INDEX idx_date ON fpd_yield(日期)")
cur.execute("CREATE INDEX idx_factory ON fpd_yield(工厂)")
cur.execute("CREATE INDEX idx_process ON fpd_yield(制程)")
cur.execute("CREATE INDEX idx_product ON fpd_yield(产品)")
conn.commit()

# 验证
cur.execute("SELECT COUNT(*) FROM fpd_yield")
count = cur.fetchone()[0]
cur.execute("SELECT * FROM fpd_yield LIMIT 3")
samples = cur.fetchall()
cur.execute("SELECT 工厂, COUNT(*) as cnt, ROUND(AVG(良率_pct),2) as avg_yield FROM fpd_yield GROUP BY 工厂")
stats = cur.fetchall()

print(f"\n✅ SQLite导入完成: {count:,} 行 | 耗时 {sqlite_time:.0f}s")
print(f"   数据库大小: {os.path.getsize(DB_PATH)/1024/1024:.0f} MB")
print(f"\n样本数据:")
for s in samples:
    print(f"  {s}")
print(f"\n按工厂统计:")
for s in stats:
    print(f"  {s[0]}: {s[1]:,}行 | 平均良率 {s[2]}%")

conn.close()
total_time = time.time() - t0
print(f"\n🎉 总耗时: {total_time:.0f}s ({total_time/60:.1f}分钟)")
