#!/usr/bin/env python3
"""通过DAA API进行1000万行平板显示良率全面分析，收集SSE结果"""
import requests
import json
import time
import re
import os

BASE = "http://localhost:5001"
SID = "620ef5a5-71c2-4b2c-bb0e-b6ad23ccd867"
OUTPUT_DIR = "/Users/viton/Data-Analysis-Agent/analysis_output_10m"
os.makedirs(OUTPUT_DIR, exist_ok=True)

ANALYSIS_QUESTIONS = [
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
    """发送聊天消息并收集SSE响应"""
    url = f"{BASE}/api/session/{SID}/chat"
    
    # 使用stream=True处理SSE
    response = requests.post(
        url,
        json={"message": message},
        stream=True,
        timeout=timeout,
        headers={"Accept": "text/event-stream"}
    )
    
    full_text = []
    charts = []
    tool_calls = []
    current_event = {}
    
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        
        if line.startswith("data: "):
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                event_type = data.get("event", "")
                
                if event_type == "text":
                    full_text.append(data.get("text", ""))
                elif event_type == "tool_call":
                    tool_name = data.get("tool_name", "")
                    tool_args = data.get("tool_args", "")
                    tool_calls.append(f"[{tool_name}] {str(tool_args)[:200]}")
                    print(f"  🔧 {tool_name}")
                elif event_type == "chart":
                    chart_id = data.get("chart_id", "")
                    chart_title = data.get("title", "")
                    charts.append({"id": chart_id, "title": chart_title})
                    print(f"  📊 图表生成: {chart_title} ({chart_id})")
                elif event_type == "thinking":
                    pass  # 思考过程，不收集
                elif event_type == "done":
                    break
                elif event_type == "stopped":
                    print("  ⚠️ 分析被中断")
                    break
            except json.JSONDecodeError:
                pass
    
    response.close()
    
    return {
        "text": "".join(full_text),
        "charts": charts,
        "tool_calls": tool_calls,
        "tool_count": len(tool_calls),
    }

# 执行所有分析
all_results = []
for i, q in enumerate(ANALYSIS_QUESTIONS):
    print(f"\n{'='*60}")
    print(f"[{i+1}/{len(ANALYSIS_QUESTIONS)}] {q['id']}")
    print(f"问题: {q['message'][:80]}...")
    print(f"{'='*60}")
    
    t0 = time.time()
    try:
        result = send_chat(q["message"], timeout=300)
        elapsed = time.time() - t0
        
        result["id"] = q["id"]
        result["message"] = q["message"]
        result["elapsed"] = elapsed
        
        all_results.append(result)
        
        # 保存结果
        output_text = f"# {q['id']}\n**Query:** {q['message']}\n\n"
        output_text += f"**Tools ({result['tool_count']}):**\n"
        for tc in result["tool_calls"]:
            output_text += f"- {tc}\n"
        output_text += f"\n**Charts:** {[c['id'] for c in result['charts']]}\n\n"
        output_text += result["text"]
        
        with open(f"{OUTPUT_DIR}/{q['id']}.md", "w") as f:
            f.write(output_text)
        
        print(f"  ✅ 完成 ({elapsed:.0f}s, {result['tool_count']} tools, {len(result['charts'])} charts)")
        print(f"  响应长度: {len(result['text'])} 字符")
        
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        all_results.append({
            "id": q["id"],
            "message": q["message"],
            "error": str(e),
            "elapsed": time.time() - t0,
        })

# 汇总
print(f"\n{'='*60}")
print(f"全部分析完成！共 {len(all_results)} 项")
print(f"{'='*60}")
for r in all_results:
    if "error" in r:
        print(f"  ❌ {r['id']}: {r['error']}")
    else:
        charts_info = ", ".join([f"{c['title']}({c['id'][:8]})" for c in r.get('charts', [])])
        print(f"  ✅ {r['id']}: {r['elapsed']:.0f}s | {r['tool_count']} tools | 图表: {charts_info}")

# 保存汇总
with open(f"{OUTPUT_DIR}/_summary.json", "w") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print(f"\n结果保存在: {OUTPUT_DIR}/")
