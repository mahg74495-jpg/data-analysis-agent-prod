#!/usr/bin/env python3
"""DAA分析 — UTF-8安全版，iter_lines正确解码"""
import requests
import json
import time
import os

BASE = "http://localhost:5001"
OUTPUT_DIR = "/Users/viton/Data-Analysis-Agent/analysis_output_10m"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 已连好DB，跳过创建session和连接

# 获取已存在的session（之前连的DB还在）
r = requests.post(f"{BASE}/api/session/new")
sid = r.json()["session_id"]
print(f"Session: {sid}")

r = requests.post(
    f"{BASE}/api/session/{sid}/connect-db",
    json={"connection_string": "sqlite:////Users/viton/Data-Analysis-Agent/data/fpd_yield_10m.db",
          "name": "平板显示良率(1000万行)"}
)
print(f"Connect DB: {r.json().get('ok', 'FAILED')}")

QUESTIONS = [
    {
        "id": "01_良率概览",
        "message": "请按工厂、制程和产品分别统计平均良率，生成对比柱状图。找出良率最高和最低的组合，给出数据分析洞察。"
    },
    {
        "id": "02_良率趋势",
        "message": "查看良率的每月变化趋势，按工厂分别展示折线图。分析是否存在良率持续改善的趋势，以及各工厂之间的差异。"
    },
    {
        "id": "03_缺陷分析",
        "message": "分析各类缺陷的分布占比（颗粒污染数、图案缺陷数、套刻偏移数、膜厚不均数、蚀刻残留数、划伤数），找出影响良率最主要的缺陷类型。生成缺陷占比饼图和缺陷-良率相关性柱状图。"
    },
    {
        "id": "04_设备参数",
        "message": "分析曝光剂量(mJ)、焦点偏移(um)、腔体压力(Torr)、RF功率(W)、研磨时间(s)、清洗液浓度(%)这6个工艺参数与良率的相关性。生成相关系数对比图，找出对良率影响最大的TOP3参数，并给出工艺优化建议。"
    },
    {
        "id": "05_异常检测",
        "message": "按工厂和月份统计良率，找出良率异常低（低于平均值2个标准差以上）的时间段。分析这些异常时段的设备参数和缺陷特征，找出可能的根因。"
    },
]

def send_chat(message, timeout=300):
    url = f"{BASE}/api/session/{sid}/chat"
    
    # 使用 iter_lines 自动处理UTF-8
    response = requests.post(
        url, json={"message": message}, stream=True,
        timeout=timeout,
        headers={"Accept": "text/event-stream"}
    )
    
    text_parts = []
    chart_ids = []
    tool_calls = []
    error_msg = None
    
    # iter_lines 自动处理 UTF-8
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        if not line.startswith("data: "):
            continue
        
        data_str = line[6:]
        if data_str == "[DONE]":
            break
        
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        
        etype = data.get("type", "")
        
        if etype == "text":
            text_parts.append(data.get("content", ""))
        elif etype == "chart_ref":
            cid = data.get("chart_id", "")
            chart_ids.append(cid)
            print(f"  📊 {cid[:12]}...")
        elif etype in ("tool_start", "tool"):
            tname = data.get("tool", data.get("name", "?"))
            tool_calls.append(tname)
            print(f"  🔧 {tname}")
        elif etype == "error":
            error_msg = data.get("message", str(data))
            print(f"  ❌ {error_msg}")
        elif etype == "done":
            break
        elif etype == "stopped":
            print(f"  ⚠️ stopped")
            break
    
    response.close()
    
    return {
        "text": "".join(text_parts),
        "chart_ids": chart_ids,
        "tool_calls": tool_calls,
        "tool_count": len(tool_calls),
        "error": error_msg,
    }

all_results = []
for i, q in enumerate(QUESTIONS):
    print(f"\n{'='*60}")
    print(f"[{i+1}/{len(QUESTIONS)}] {q['id']}")
    print(f"{'='*60}")
    
    t0 = time.time()
    try:
        result = send_chat(q["message"], timeout=300)
        elapsed = time.time() - t0
        result["id"] = q["id"]
        result["message"] = q["message"]
        result["elapsed"] = elapsed
        
        all_results.append(result)
        
        # 保存
        content = (f"# {q['id']}\n**Query:** {q['message']}\n\n"
                   f"**Tools ({result['tool_count']}):**\n")
        for tc in result["tool_calls"]:
            content += f"- [{tc}]\n"
        content += f"\n**Charts:** {result['chart_ids']}\n\n"
        content += result["text"]
        
        with open(f"{OUTPUT_DIR}/{q['id']}.md", "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"  ✅ ({elapsed:.0f}s, {result['tool_count']} tools, {len(result['chart_ids'])} charts, {len(result['text'])} chars)")
    except Exception as e:
        print(f"  ❌ {e}")
        all_results.append({"id": q["id"], "message": q["message"], "error": str(e)})

print(f"\n全部分析完成！共 {len(all_results)} 项")
with open(f"{OUTPUT_DIR}/_summary.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
