#!/usr/bin/env python3
"""Run analysis queries via DAA SSE API and collect results"""
import json, urllib.request, http.client, ssl, time, re, os

SID = 'ffff1e7a-085a-403e-a34b-1be35ac8cef4'
BASE = 'localhost:5001'
OUTDIR = '/Users/viton/Data-Analysis-Agent/analysis_output'
os.makedirs(OUTDIR, exist_ok=True)

def send_chat(message, save_label):
    """Send chat via SSE and collect full response"""
    conn = http.client.HTTPConnection(BASE, timeout=120)
    body = json.dumps({'message': message}).encode()
    headers = {'Content-Type': 'application/json', 'Accept': 'text/event-stream'}
    conn.request('POST', f'/api/session/{SID}/chat', body=body, headers=headers)
    
    resp = conn.getresponse()
    print(f"\n{'='*60}")
    print(f"[{save_label}] HTTP {resp.status}")
    print(f"[{save_label}] Query: {message}")
    
    full_text = []
    charts = []
    tool_steps = []
    last_event = None
    
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
                        last_event = 'DONE'
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
                            print(f"  !! ERROR: {evt.get('message','')}")
                        elif t == 'done':
                            last_event = 'DONE'
                    except json.JSONDecodeError:
                        pass
    conn.close()
    
    result = ''.join(full_text)
    
    # Save result
    out_path = f'{OUTDIR}/{save_label}.md'
    with open(out_path, 'w') as f:
        f.write(f'# {save_label}\n\n')
        f.write(f'**Query:** {message}\n\n')
        f.write(f'**Tools called:**\n')
        for s in tool_steps:
            f.write(f'- {s}\n')
        f.write(f'\n**Charts:** {charts}\n\n')
        f.write(f'**Response:**\n\n{result}\n')
    
    # Print summary
    print(f"  Tools: {len(tool_steps)} steps")
    for s in tool_steps[:10]:
        print(f"    {s}")
    print(f"  Charts: {len(charts)} → {charts}")
    print(f"  Response length: {len(result)} chars")
    print(f"  Response preview:\n{result[:800]}")
    print(f"\n  Saved to: {out_path}")
    
    return {'text': result, 'charts': charts, 'tools': tool_steps}

# --- Analysis 1: Overall yield overview ---
send_chat('请按产线和产品型号分别统计平均良率，并生成对比图表', '01_良率概览')
