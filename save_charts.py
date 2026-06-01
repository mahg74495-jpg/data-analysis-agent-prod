#!/usr/bin/env python3
"""Download all chart images from DAA and save screenshots"""
import urllib.request, os, json

OUTDIR = '/Users/viton/Data-Analysis-Agent/analysis_output'
CHART_DIR = f'{OUTDIR}/charts'
os.makedirs(CHART_DIR, exist_ok=True)

# All chart IDs from the 4 analyses
all_charts = {
    '01_良率概览_分组柱状图': '649113b1b7854f5995aeb2ba2191d182',
    '02_良率趋势_折线图': '5392c87c450640318b76b7f405d6a657',
    '03_缺陷分布_饼图': 'a0785616c51442b5b260913dc5328a73',
    '03_缺陷相关性_条形图': '1657841dc5c242989759a5bfcedf045a',
    '04_成膜温度_散点图': '52c0fb5269e74f4aa8db6a99264410bc',
    '04_真空度_散点图': '4d968c52f65d4db08ff73267915962d7',
    '04_对位误差_散点图': '5cdf93fb6805424db05c82f736dfc65b',
    '04_曝光时间_散点图': '71eeb6c4e349159e5a634dd9c5508b',
}

for name, chart_id in all_charts.items():
    url = f'http://localhost:5001/api/chart/{chart_id}'
    path = f'{CHART_DIR}/{name}.html'
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        html = resp.read().decode('utf-8')
        with open(path, 'w') as f:
            f.write(html)
        print(f'✓ {name} → {path} ({len(html)} bytes)')
    except Exception as e:
        print(f'✗ {name}: {e}')

print(f'\nAll charts saved to {CHART_DIR}')
print(f'Total: {len(os.listdir(CHART_DIR))} files')
