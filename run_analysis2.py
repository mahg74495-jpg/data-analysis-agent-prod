#!/usr/bin/env python3
"""Run analysis query #2: time trend + defect analysis"""
import json, http.client, os, time

SID = 'ffff1e7a-085a-403e-a34b-1be35ac8cef4'
BASE = 'localhost:5001'
OUTDIR = '/Users/viton/Data-Analysis-Agent/analysis_output'

def send_chat(message, save_label):
    conn = http.client.HTTPConnection(BASE, timeout=180)
    body = json.dumps({'message': message}).encode()
    headers = {'Content-Type': 'application/json', 'Accept': 'text/event-stream'}
    conn.request('POST', f'/api/session/{SID}/chat', body=body, headers=headers)
    
    resp = conn.getresponse()
    print(f"\n{'='*60}")
    print(f"[{save_label}] HTTP {resp.status}")
    
    full_text = []
    charts = []
    tool_steps = []
    
    buffer = b''
    while True:
        chunk = resp.read(4096)
        if not chunk:
            break
        buffer += chunk
        while b'\n\n' in buffer:
            raw, buffer = buffer.split(b'\n\n', 1)
            text = raw.decode('utf-8', errors='replace')
            for line in text.split('\n'):
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str.strip() == '[DONE]':
                        continue
                    try:
                        evt = json.loads(data_str)
                        t = evt.get('type','')
                        if t == 'text_delta':
                            full_text.append(evt.get('content',''))
                        elif t == 'text':
                            full_text.append(evt.get('content',''))
                        elif t == 'chart_ref':
                            charts.append(evt.get('chart_id',''))
                        elif t == 'tool_start':
                            tool_steps.append(f"[{evt.get('tool','')}] {evt.get('display','')}")
                        elif t == 'error':
                            print(f"  ERROR: {evt.get('message','')}")
                    except json.JSONDecodeError:
                        pass
    conn.close()
    
    result = ''.join(full_text)
    out_path = f'{OUTDIR}/{save_label}.md'
    with open(out_path, 'w') as f:
        f.write(f'# {save_label}\n\n**Query:** {message}\n\n')
        f.write(f'**Tools:** {len(tool_steps)} steps\n')
        for s in tool_steps:
            f.write(f'- {s}\n')
        f.write(f'\n**Charts:** {charts}\n\n{result}\n')
    
    print(f"  Tools: {len(tool_steps)} → {tool_steps}")
    print(f"  Charts: {charts}")
    print(f"  Preview: {result[:600]}")
    print(f"  Saved: {out_path}")
    return {'text': result, 'charts': charts}

# Analysis 2: Time trend
send_chat('查看整个数据期间（3月到5月）良率的每日变化趋势，按产线分别展示，生成折线图', '02_良率趋势')

# Analysis 3: Defect analysis
send_chat('分析各缺陷类型（点缺陷、线缺陷、Mura、异物、划伤、色偏、亮度不均）的分布占比，以及哪种缺陷是导致良率下降的主要原因', '03_缺陷分析')
