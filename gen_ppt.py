#!/usr/bin/env python3
"""
Two-phase PPT generation via DAA API:
  Phase 1: /ppt → propose_ppt_outline → collect ppt_outline event
  Phase 2: ppt_confirm → generate_ppt → download .pptx
"""
import json, http.client, os, re, shutil, io

SID = 'ffff1e7a-085a-403e-a34b-1be35ac8cef4'
BASE = 'localhost:5001'
OUTPUT = '/Users/viton/Desktop/'

def sse_stream(json_body, timeout=300):
    """Send POST and yield parsed SSE events"""
    conn = http.client.HTTPConnection(BASE, timeout=timeout)
    body = json.dumps(json_body).encode()
    headers = {'Content-Type': 'application/json', 'Accept': 'text/event-stream'}
    conn.request('POST', f'/api/session/{SID}/chat', body=body, headers=headers)
    resp = conn.getresponse()
    
    buffer = b''
    while True:
        chunk = resp.read(8192)
        if not chunk:
            break
        buffer += chunk
        while b'\n\n' in buffer:
            raw, buffer = buffer.split(b'\n\n', 1)
            for line in raw.decode('utf-8', errors='replace').split('\n'):
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str.strip() == '[DONE]':
                        continue
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        pass
    conn.close()

# ═══════════════════════════════════════════
# Phase 1: Send /ppt command
# ═══════════════════════════════════════════
print("=" * 60)
print("Phase 1: Sending /ppt command...")
print("=" * 60)

ppt_title = None
ppt_slides = None
all_text = []

for evt in sse_stream({
    'message': '请基于前面的良率分析结果，生成一份专业的PPT报告。必须使用之前分析中实际查询到的数据，不要编造数字。\n\n包含以下内容：\n1. 封面 + 目录\n2. 整体良率概览（产线×产品对比表 + 关键数字）\n3. 良率时间趋势分析\n4. 缺陷分布与影响分析\n5. 设备参数相关性分析\n6. 改进建议\n7. 结束页',
    'command': 'ppt'
}):
    t = evt.get('type', '')
    
    if t == 'tool_start':
        print(f"  [{evt.get('tool','')}] {evt.get('display','')}")
    elif t == 'tool_end':
        pass
    elif t == 'text_delta':
        all_text.append(evt.get('content', ''))
    elif t == 'text':
        all_text.append(evt.get('content', ''))
    elif t == 'ppt_outline':
        ppt_title = evt.get('title', '')
        ppt_slides = evt.get('slides', [])
        print(f"\n  ✓ PPT Outline: '{ppt_title}' — {len(ppt_slides)} slides")
        for i, s in enumerate(ppt_slides[:3], 1):
            layout = s.get('layout', '?')
            params_keys = [k for k in s if k != 'layout']
            print(f"    #{i} {layout}: {params_keys}")
        if len(ppt_slides) > 3:
            print(f"    ... and {len(ppt_slides) - 3} more slides")
    elif t == 'error':
        print(f"  ✗ ERROR: {evt.get('message','')}")
    elif t == 'done':
        print("  Phase 1 done.")

if not ppt_title or not ppt_slides:
    print("\n✗ Phase 1 failed: no ppt_outline received")
    print("Full text:", ''.join(all_text)[:500])
    exit(1)

print(f"\nPhase 1 complete: {len(ppt_slides)} slides")

# ═══════════════════════════════════════════
# Phase 2: Confirm and generate
# ═══════════════════════════════════════════
print("\n" + "=" * 60)
print("Phase 2: Confirming PPT generation...")
print("=" * 60)

full_text_p2 = []
ppt_file_url = None
ppt_filename = None

for evt in sse_stream({
    'message': '确认生成PPT',
    'command': 'ppt_confirm',
    'ppt_title': ppt_title,
    'ppt_slides': ppt_slides
}):
    t = evt.get('type', '')
    if t == 'tool_start':
        print(f"  [{evt.get('tool','')}] {evt.get('display','')}")
    elif t == 'text':
        content = evt.get('content', '')
        full_text_p2.append(content)
        print(f"  Response: {content[:200]}")
        # Extract download URL
        match = re.search(r'\[.*?\]\(/api/export/([^)]+)\)', content)
        if match:
            ppt_filename = match.group(1)
            ppt_file_url = f'/api/export/{ppt_filename}'
    elif t == 'error':
        print(f"  ✗ ERROR: {evt.get('message','')}")
    elif t == 'done':
        print("  Phase 2 done.")

if not ppt_filename:
    print("\n✗ Phase 2 failed: no PPT file generated")
    print("Full text:", ''.join(full_text_p2)[:500])
    exit(1)

# ═══════════════════════════════════════════
# Phase 3: Download PPT
# ═══════════════════════════════════════════
print("\n" + "=" * 60)
print(f"Phase 3: Downloading PPT: {ppt_filename}")
print("=" * 60)

conn = http.client.HTTPConnection(BASE, timeout=30)
conn.request('GET', f'/api/export/{ppt_filename}')
resp = conn.getresponse()
if resp.status == 200:
    ppt_data = resp.read()
    dest = os.path.join(OUTPUT, ppt_filename)
    with open(dest, 'wb') as f:
        f.write(ppt_data)
    import os
    size_kb = len(ppt_data) / 1024
    print(f"  ✓ Downloaded: {dest} ({size_kb:.1f} KB)")
    print(f"\nPPT FILE PATH: {dest}")
else:
    print(f"  ✗ Download failed: HTTP {resp.status}")
conn.close()
