#!/usr/bin/env python3
"""Generate semiconductor display manufacturing yield dataset - wafer level"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

np.random.seed(7)

dates = [datetime(2026, 3, 1) + timedelta(days=i) for i in range(90)]
fabs = ['Fab-A', 'Fab-B', 'Fab-C']
processes = ['光刻', '刻蚀', '沉积', 'CMP', '离子注入', '清洗']
products = ['OLED驱动IC', 'LCD驱动IC', 'MicroLED背板', 'TFT阵列']
defect_types = ['颗粒污染', '图案缺陷', '套刻偏移', '膜厚不均', '蚀刻残留', 'CMP划伤']
equip_params = ['曝光剂量', '焦点偏移', '腔体压力', 'RF功率', '研磨时间', '清洗液浓度']

records = []
for i, date in enumerate(dates):
    for fab in fabs:
        for process in np.random.choice(processes, size=np.random.randint(3, 7), replace=False):
            for product in np.random.choice(products, size=np.random.randint(1, 4), replace=False):
                # Wafer input
                wafers = int(np.random.normal(200, 30))
                wafers = max(80, min(300, wafers))
                
                # Yield - base + fab effect + process effect + product effect + trend
                base_yield = 94.0
                fab_effect = {'Fab-A': 1.8, 'Fab-B': 0.3, 'Fab-C': -1.5}[fab]
                process_effect = {
                    '光刻': -1.0, '刻蚀': -0.5, '沉积': 0.8,
                    'CMP': -1.5, '离子注入': -0.3, '清洗': 0.5
                }[process]
                product_effect = {
                    'OLED驱动IC': -2.0, 'LCD驱动IC': 1.0,
                    'MicroLED背板': -3.0, 'TFT阵列': -0.5
                }[product]
                # Tool aging: slight decline then recovery after maintenance at day 55
                tool_aging = -1.5 if 40 <= i <= 55 else 0
                # Process improvement at day 60
                improvement = 2.0 if i >= 60 else 0
                
                yield_pct = base_yield + fab_effect + process_effect + product_effect + tool_aging + improvement + np.random.normal(0, 1.5)
                yield_pct = max(55, min(99.8, yield_pct))
                
                good_wafers = int(wafers * yield_pct / 100)
                defect_wafers = wafers - good_wafers
                
                # Defect distribution
                weights = [0.28, 0.22, 0.15, 0.13, 0.12, 0.10]
                if defect_wafers > 0:
                    defect_counts = np.random.multinomial(defect_wafers, weights / np.sum(weights))
                else:
                    defect_counts = [0] * 6
                
                # Equipment parameters
                dose = np.random.normal(45.0, 3.0)
                focus = np.random.normal(0.0, 0.08)
                pressure = np.random.normal(0.5, 0.06)
                rf_power = np.random.normal(300.0, 15.0)
                cmp_time = np.random.normal(120.0, 8.0)
                conc = np.random.normal(2.5, 0.3)
                
                records.append({
                    '日期': date.strftime('%Y-%m-%d'),
                    '晶圆厂': fab,
                    '制程': process,
                    '产品': product,
                    '投入晶圆数': wafers,
                    '良品晶圆数': good_wafers,
                    '不良数': defect_wafers,
                    '良率(%)': round(yield_pct, 2),
                    '曝光剂量(mJ)': round(dose, 2),
                    '焦点偏移(μm)': round(focus, 4),
                    '腔体压力(Torr)': round(pressure, 4),
                    'RF功率(W)': round(rf_power, 1),
                    '研磨时间(s)': round(cmp_time, 1),
                    '清洗液浓度(%)': round(conc, 2),
                    '颗粒污染数': int(defect_counts[0]),
                    '图案缺陷数': int(defect_counts[1]),
                    '套刻偏移数': int(defect_counts[2]),
                    '膜厚不均数': int(defect_counts[3]),
                    '蚀刻残留数': int(defect_counts[4]),
                    'CMP划伤数': int(defect_counts[5]),
                })

df = pd.DataFrame(records)
df = df.sort_values(['日期', '晶圆厂', '制程', '产品']).reset_index(drop=True)

path = '/Users/viton/Data-Analysis-Agent/uploads/半导体显示良率数据.csv'
df.to_csv(path, index=False, encoding='utf-8-sig')
print(f'Rows: {len(df)}  Date: {df["日期"].min()} ~ {df["日期"].max()}')
print(f'Overall yield: {df["良率(%)"].mean():.2f}%')
print(f'\n晶圆厂良率:')
print(df.groupby('晶圆厂')['良率(%)'].agg(['mean','count']).round(2).to_string())
print(f'\n制程良率:')
print(df.groupby('制程')['良率(%)'].agg(['mean','count']).round(2).to_string())
print(f'\n产品良率:')
print(df.groupby('产品')['良率(%)'].agg(['mean','count']).round(2).to_string())
print(f'\nPath: {path}')
