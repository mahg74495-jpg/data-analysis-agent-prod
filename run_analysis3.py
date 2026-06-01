#!/usr/bin/env python3
"""Run analysis #4: equipment parameters correlation + improvements"""
import json, http.client, os

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
                        if t in ('text_delta','text'):
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
        f.write(f'**Tools:** {len(tool_steps)}\n')
        for s in tool_steps:
            f.write(f'- {s}\n')
        f.write(f'\n**Charts:** {charts}\n\n{result}\n')
    
    print(f"  Tools: {len(tool_steps)}")
    print(f"  Charts: {charts}")
    print(f"  Preview: {result[:800]}")
    print(f"  Saved: {out_path}")
    return {'text': result, 'charts': charts}

# Analysis 4: Equipment parameters correlation
send_chat('分析成膜温度、真空度、对位误差、曝光时间这4个设备参数与良率的相关性，找出哪个参数对良率影响最大，生成散点图', '04_设备参数')
