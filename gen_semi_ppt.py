#!/usr/bin/env python3
"""
半导体显示良率分析全流程：
  1. 上传数据 + 配置 LLM
  2. 运行 4 个分析
  3. 生成 PPT
  4. 保存结果
"""
import json, urllib.request, http.client, os, re, uuid, io

SID = str(uuid.uuid4())
BASE = 'localhost:5001'
OUTDIR = '/Users/viton/Data-Analysis-Agent/analysis_output_semi'
os.makedirs(OUTDIR, exist_ok=True)

def sse_stream(sid, json_body, timeout=300):
    conn = http.client.HTTPConnection(BASE, timeout=timeout)
    body = json.dumps(json_body).encode()
    headers = {'Content-Type': 'application/json', 'Accept': 'text/event-stream'}
    conn.request('POST', f'/api/session/{sid}/chat', body=body, headers=headers)
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
                    ds = line[6:]
                    if ds.strip() == '[DONE]': continue
                    try: yield json.loads(ds)
                    except json.JSONDecodeError: pass
    conn.close()

def save_result(label, query, text, charts, tools):
    with open(f'{OUTDIR}/{label}.md', 'w') as f:
        f.write(f'# {label}\n**Query:** {query}\n\n**Tools ({len(tools)}):**\n')
        for t in tools: f.write(f'- {t}\n')
        f.write(f'\n**Charts:** {charts}\n\n{text}\n')

# ═══════════ STEP 1: Upload ─══════════
print("STEP 1: Uploading data...")
csv_path = '/Users/viton/Data-Analysis-Agent/uploads/半导体显示良率数据.csv'
boundary = '----Boundary' + uuid.uuid4().hex
body = io.BytesIO()
with open(csv_path, 'rb') as f:
    fb = f.read()
body.write(f'--{boundary}\r\n'.encode())
body.write(b'Content-Disposition: form-data; name="file"; filename="semi_yield.csv"\r\n')
body.write(b'Content-Type: text/csv\r\n\r\n')
body.write(fb)
body.write(f'\r\n--{boundary}--\r\n'.encode())
conn = http.client.HTTPConnection(BASE, timeout=30)
conn.request('POST', f'/api/session/{SID}/upload',
             body=body.getvalue(),
             headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
resp = conn.getresponse()
result = json.loads(resp.read().decode())
conn.close()
print(f"  Upload: ok={result.get('ok')}, rows={result.get('schema_preview','')[:100]}")

# ═══════════ STEP 2: Config LLM ─══════
print("\nSTEP 2: Configuring LLM...")
env = os.path.expanduser('~/.hermes/.env')
api_key = None
with open(env) as f:
    for line in f:
        m = re.match(r'DEEPSEEK_API_KEY\s*=\s*(.+)', line.strip())
        if m and not line.strip().startswith('#'):
            api_key = m.group(1).strip().strip('"').strip("'")
            break
if not api_key:
    print("FATAL: No API key"); exit(1)

data = json.dumps({
    'provider': 'deepseek', 'api_key': api_key,
    'base_url': 'https://api.deepseek.com', 'model': 'deepseek-chat',
    'enable_thinking': False, 'context_window': 64000, 'max_output_tokens': 8192
}).encode()
urllib.request.urlopen(urllib.request.Request(
    'http://localhost:5001/api/models/set-builtin',
    data=data, headers={'Content-Type': 'application/json'}
))
print("  LLM configured ✓")

# ═══════════ STEP 3: Run Analyses (1-3) ═══════════
analyses = [
    ('01_良率概览', '请按晶圆厂、制程和产品分别统计平均良率，生成对比图表'),
    ('02_良率趋势', '查看良率的每日变化趋势，按晶圆厂分别展示折线图'),
    ('03_缺陷分析', '分析各类缺陷的分布占比及与良率的相关性，找出影响良率最主要的缺陷类型'),
]

for label, query in analyses:
    print(f"\n{'='*50}")
    print(f"Analysis: {label}")
    full_text, charts, tools = [], [], []
    for evt in sse_stream(SID, {'message': query}):
        t = evt.get('type','')
        if t == 'tool_start':
            tools.append(f"[{evt.get('tool','')}] {evt.get('display','')[:60]}")
            print(f"  [{evt.get('tool','')}] {evt.get('display','')[:60]}")
        elif t in ('text_delta','text'):
            full_text.append(evt.get('content',''))
        elif t == 'chart_ref':
            charts.append(evt.get('chart_id',''))
        elif t == 'error':
            print(f"  ERROR: {evt.get('message','')}")
    text = ''.join(full_text)
    save_result(label, query, text, charts, tools)
    print(f"  Charts: {charts} | Text: {len(text)} chars")

# ═══════════ STEP 4: Analysis 4 - Equipment ═══════════
print(f"\n{'='*50}")
print("Analysis: 04_设备参数")
query4 = '分析曝光剂量、焦点偏移、腔体压力、RF功率、研磨时间、清洗液浓度这6个参数与良率的相关性，找出对良率影响最大的参数'
full_text, charts, tools = [], [], []
for evt in sse_stream(SID, {'message': query4}):
    t = evt.get('type','')
    if t == 'tool_start':
        tools.append(f"[{evt.get('tool','')}] {evt.get('display','')[:60]}")
        print(f"  [{evt.get('tool','')}] {evt.get('display','')[:60]}")
    elif t in ('text_delta','text'):
        full_text.append(evt.get('content',''))
    elif t == 'chart_ref':
        charts.append(evt.get('chart_id',''))
    elif t == 'error':
        print(f"  ERROR: {evt.get('message','')}")
text = ''.join(full_text)
save_result('04_设备参数', query4, text, charts, tools)
print(f"  Charts: {charts} | Text: {len(text)} chars")

# ═══════════ STEP 5: PPT ═══════════
print(f"\n{'='*50}")
print("STEP 5: PPT Generation — Phase 1 (/ppt)")

ppt_title = None; ppt_slides = None
for evt in sse_stream(SID, {
    'message': '请基于前面的半导体显示良率分析结果生成专业PPT报告。使用实际查询数据。包含：封面、目录、良率概览、时间趋势、缺陷分析、设备参数、改进建议、结论',
    'command': 'ppt'
}):
    t = evt.get('type','')
    if t == 'tool_start':
        print(f"  [{evt.get('tool','')}] {evt.get('display','')[:80]}")
    elif t == 'ppt_outline':
        ppt_title = evt.get('title',''); ppt_slides = evt.get('slides',[])
        print(f"  Outline: '{ppt_title}' — {len(ppt_slides)} slides")

if not ppt_title:
    print("PPT outline failed!")
    exit(1)

# Phase 2: Confirm
print(f"\nSTEP 6: PPT Generation — Phase 2 (confirm)")
ppt_result = []
ppt_file = None
for evt in sse_stream(SID, {
    'message': '确认', 'command': 'ppt_confirm',
    'ppt_title': ppt_title, 'ppt_slides': ppt_slides
}):
    t = evt.get('type','')
    if t == 'tool_start':
        print(f"  [{evt.get('tool','')}] {evt.get('display','')}")
    elif t == 'text':
        content = evt.get('content','')
        ppt_result.append(content)
        m = re.search(r'\[.*?\]\(/api/export/([^)]+)\)', content)
        if m: ppt_file = m.group(1)
        print(f"  Result: {content[:200]}")

# Download PPT
if ppt_file:
    from urllib.request import urlopen, quote
    url = f'http://localhost:5001/api/export/{quote(ppt_file)}'
    data = urlopen(url, timeout=30).read()
    dest = f'/Users/viton/Desktop/{ppt_file}'
    with open(dest, 'wb') as f: f.write(data)
    print(f"\n  PPT saved: {dest} ({len(data)/1024:.1f} KB)")
    print(f"\nPPT_PATH={dest}")
else:
    print("PPT download failed!")

print(f"\nDONE. SID={SID}")
