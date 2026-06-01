#!/usr/bin/env python3
"""CSV → SQLite 批量导入（1000万行）"""
import sqlite3
import csv
import os
import time

CSV_PATH = "/Users/viton/Data-Analysis-Agent/uploads/平板显示良率_1000万.csv"
DB_PATH = "/Users/viton/Data-Analysis-Agent/data/fpd_yield_10m.db"

t0 = time.time()

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=OFF")
conn.execute("PRAGMA synchronous=OFF")
conn.execute("PRAGMA cache_size=1000000")
conn.execute("PRAGMA temp_store=MEMORY")

cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS fpd_yield (
    日期 TEXT, 工厂 TEXT, 制程 TEXT, 产品 TEXT,
    投入基板数 INTEGER, 良品基板数 INTEGER, 不良数 INTEGER, 良率_pct REAL,
    曝光剂量_mJ REAL, 焦点偏移_um REAL, 腔体压力_Torr REAL,
    RF功率_W REAL, 研磨时间_s REAL, 清洗液浓度_pct REAL,
    颗粒污染数 INTEGER, 图案缺陷数 INTEGER, 套刻偏移数 INTEGER,
    膜厚不均数 INTEGER, 蚀刻残留数 INTEGER, 划伤数 INTEGER
)
""")

# Read CSV and batch insert
BATCH_SIZE = 100000
batch = []
total = 0

with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        batch.append((
            row["日期"], row["工厂"], row["制程"], row["产品"],
            int(row["投入基板数"]), int(row["良品基板数"]), int(row["不良数"]),
            float(row["良率(%)"]), float(row["曝光剂量(mJ)"]), float(row["焦点偏移(μm)"]),
            float(row["腔体压力(Torr)"]), float(row["RF功率(W)"]),
            float(row["研磨时间(s)"]), float(row["清洗液浓度(%)"]),
            int(row["颗粒污染数"]), int(row["图案缺陷数"]), int(row["套刻偏移数"]),
            int(row["膜厚不均数"]), int(row["蚀刻残留数"]), int(row["划伤数"])
        ))
        if len(batch) >= BATCH_SIZE:
            cur.executemany("INSERT INTO fpd_yield VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
            conn.commit()
            total += len(batch)
            elapsed = time.time() - t0
            print(f"  {total:,} / 10,000,000 | {elapsed:.0f}s | {total/elapsed:.0f} rows/s")
            batch = []

if batch:
    cur.executemany("INSERT INTO fpd_yield VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
    conn.commit()
    total += len(batch)

print(f"\n✅ 导入完成: {total:,} 行 | 耗时 {time.time()-t0:.0f}s")

# 建索引
print("📊 建索引...")
cur.execute("CREATE INDEX IF NOT EXISTS idx_date ON fpd_yield(日期)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_factory ON fpd_yield(工厂)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_process ON fpd_yield(制程)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_product ON fpd_yield(产品)")
conn.commit()

# 验证
cur.execute("SELECT COUNT(*) FROM fpd_yield")
print(f"总数: {cur.fetchone()[0]:,}")
cur.execute("SELECT 工厂, COUNT(*) c, ROUND(AVG(良率_pct),2) y FROM fpd_yield GROUP BY 工厂 ORDER BY c DESC")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]:,}行 | 平均良率 {r[2]}%")

db_size = os.path.getsize(DB_PATH)/1024/1024
print(f"\n数据库大小: {db_size:.0f} MB")
conn.close()
