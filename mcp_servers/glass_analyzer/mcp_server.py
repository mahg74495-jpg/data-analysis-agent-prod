#!/usr/bin/env python3
"""
玻璃四站点差异分析 — MCP Server
通过 stdio 协议接入 DAA (Data Analysis Agent)

提供工具:
  - glass_import: 导入玻璃测试数据
  - glass_analyze: 执行四站点差异分析
  - glass_report: 查看最近的分析报告
"""
import sys
import json
import os
import subprocess
import glob
from pathlib import Path
from typing import Any, Optional

# ── 配置 ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
ANALYZE_SCRIPT = BASE_DIR / "analyze.py"
IMPORT_SCRIPT = BASE_DIR / "import_data.py"

# ── MCP 协议工具 ──────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "glass_import",
        "description": "导入玻璃测试数据（CSV/Excel），支持三种模式：\n"
                       "1) 单文件宽表（含 station_A/B/C/D 列）\n"
                       "2) 多文件（每个站点一个文件）\n"
                       "3) 长表（含 station 和 value 列）\n"
                       "导入后自动保存为 Parquet，供 glass_analyze 使用。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "数据文件路径（单文件模式）"
                },
                "dir_path": {
                    "type": "string",
                    "description": "数据目录路径（多文件模式，每个站点一个文件）"
                },
                "file_pattern": {
                    "type": "string",
                    "description": "文件匹配模式，默认 *.csv",
                    "default": "*.csv"
                },
                "station_map": {
                    "type": "string",
                    "description": "文件名→站点映射JSON，如 {\"a.csv\":\"A\",\"b.csv\":\"B\"}（多文件模式）"
                },
                "panel_col": {"type": "string", "description": "玻璃编号列名"},
                "point_col": {"type": "string", "description": "点位编号列名"},
                "row_col": {"type": "string", "description": "行坐标列名"},
                "col_col": {"type": "string", "description": "列坐标列名"},
                "station_col": {"type": "string", "description": "站点列名（长表模式）"},
                "value_col": {"type": "string", "description": "数值列名（长表模式）"},
                "output_name": {
                    "type": "string",
                    "description": "输出文件名（不含扩展名），默认 imported_data",
                    "default": "imported_data"
                },
            },
            "required": [],
        },
    },
    {
        "name": "glass_analyze",
        "description": "执行四站点差异分析。\n"
                       "计算 A/B/C/D 四个站点两两之间的差异（RMSE/MAE/P95/最大差异等），\n"
                       "生成热力图、分布图、玻璃对比图、空间误差图。\n"
                       "分析结果保存到 output/ 目录。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Parquet数据文件路径（默认自动找 data/ 下最新的）"
                },
                "panel": {
                    "type": "integer",
                    "description": "热力图显示的玻璃编号（默认 0）",
                    "default": 0
                },
            },
            "required": [],
        },
    },
    {
        "name": "glass_report",
        "description": "查看最近的分析报告。返回最新的 JSON 报告内容和图表文件列表。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "report_index": {
                    "type": "integer",
                    "description": "报告索引（0=最新，1=次新），默认 0",
                    "default": 0
                },
            },
            "required": [],
        },
    },
    {
        "name": "glass_status",
        "description": "查看玻璃分析系统的状态：数据文件、报告文件、磁盘占用。",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ── 工具实现 ──────────────────────────────────────────────────────────────────

def _run_script(script_path: str, args: list[str]) -> str:
    """运行 Python 脚本并返回输出"""
    result = subprocess.run(
        [sys.executable, script_path] + args,
        capture_output=True, text=True, timeout=120,
        cwd=str(BASE_DIR),
    )
    output = result.stdout
    if result.stderr:
        output += "\n[STDERR]\n" + result.stderr
    if result.returncode != 0:
        output = f"❌ 脚本退出码 {result.returncode}\n{output}"
    return output.strip()


def _handle_import(args: dict) -> str:
    """处理数据导入"""
    cmd_args = []
    
    if args.get("file_path"):
        cmd_args += ["--file", args["file_path"]]
    elif args.get("dir_path"):
        cmd_args += ["--dir", args["dir_path"]]
        if args.get("file_pattern"):
            cmd_args += ["--pattern", args["file_pattern"]]
    else:
        return "❌ 请指定 --file（单文件）或 --dir（多文件目录）"
    
    if args.get("station_map"):
        cmd_args += ["--station_map", args["station_map"]]
    if args.get("panel_col"): cmd_args += ["--panel_col", args["panel_col"]]
    if args.get("point_col"): cmd_args += ["--point_col", args["point_col"]]
    if args.get("row_col"): cmd_args += ["--row_col", args["row_col"]]
    if args.get("col_col"): cmd_args += ["--col_col", args["col_col"]]
    if args.get("station_col"): cmd_args += ["--station_col", args["station_col"]]
    if args.get("value_col"): cmd_args += ["--value_col", args["value_col"]]
    if args.get("output_name"): cmd_args += ["--output", args["output_name"]]
    
    return _run_script(str(IMPORT_SCRIPT), cmd_args)


def _handle_analyze(args: dict) -> str:
    """处理差异分析"""
    cmd_args = []
    if args.get("file"):
        cmd_args += ["--file", args["file"]]
    if args.get("panel") is not None:
        cmd_args += ["--panel", str(args["panel"])]
    return _run_script(str(ANALYZE_SCRIPT), cmd_args)


def _handle_report(args: dict) -> str:
    """查看最近的分析报告"""
    report_files = sorted(OUTPUT_DIR.glob("analysis_report.json"))
    if not report_files:
        return "❌ 没有找到分析报告，请先运行 glass_analyze"
    
    idx = args.get("report_index", 0)
    if idx >= len(report_files):
        return f"❌ 报告索引 {idx} 超出范围，只有 {len(report_files)} 份报告"
    
    report_path = report_files[-(idx + 1)]
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    
    # 找对应的图表
    png_files = sorted(OUTPUT_DIR.glob("*.png"))
    
    lines = []
    lines.append(f"📊 **分析报告** ({report['报告信息']['生成时间']})")
    lines.append(f"   玻璃数: {report['报告信息']['玻璃数']}  每片点数: {report['报告信息']['每片点数']}")
    lines.append("")
    lines.append("**差异表征参数:**")
    lines.append(f"{'站点对':<10} {'RMSE':<10} {'MAE':<10} {'P95':<10} {'最大差异':<10} {'平均偏差':<10}")
    lines.append("-" * 60)
    for pair_name, params in report["差异表征参数"].items():
        lines.append(f"{pair_name:<10} {params['RMSE']:<10.4f} {params['MAE']:<10.4f} "
                     f"{params['P95差异']:<10.4f} {params['最大差异']:<10.4f} "
                     f"{params['平均偏差']:<10.4f}")
    
    lines.append("")
    lines.append(f"**图表文件:**")
    for png in png_files:
        lines.append(f"  - {png.name}")
    
    return "\n".join(lines)


def _handle_status(args: dict) -> str:
    """查看系统状态"""
    lines = []
    lines.append("🔍 **玻璃分析系统状态**")
    lines.append("")
    
    # 数据文件
    parquet_files = list(DATA_DIR.glob("*.parquet"))
    csv_files = list(DATA_DIR.glob("*.csv"))
    lines.append(f"**数据文件:**")
    lines.append(f"  Parquet: {len(parquet_files)} 个")
    for f in parquet_files:
        size_mb = os.path.getsize(f) / 1024 / 1024
        lines.append(f"    - {f.name} ({size_mb:.2f} MB)")
    lines.append(f"  CSV: {len(csv_files)} 个")
    
    # 报告文件
    report_files = list(OUTPUT_DIR.glob("analysis_report.json"))
    png_files = list(OUTPUT_DIR.glob("*.png"))
    lines.append(f"")
    lines.append(f"**报告文件:**")
    lines.append(f"  JSON报告: {len(report_files)} 份")
    lines.append(f"  图表: {len(png_files)} 张")
    
    # 磁盘占用
    total_size = sum(
        os.path.getsize(f) for f in list(DATA_DIR.glob("*")) + list(OUTPUT_DIR.glob("*"))
    ) / 1024 / 1024
    lines.append(f"")
    lines.append(f"**磁盘占用:** {total_size:.2f} MB")
    
    return "\n".join(lines)


# ── 工具路由 ──────────────────────────────────────────────────────────────────

TOOL_HANDLERS = {
    "glass_import": _handle_import,
    "glass_analyze": _handle_analyze,
    "glass_report": _handle_report,
    "glass_status": _handle_status,
}


# ── MCP 协议处理器 ────────────────────────────────────────────────────────────

def handle_request(request: dict) -> Optional[dict]:
    """处理 JSON-RPC 请求"""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "glass-diff-analyzer",
                    "version": "1.0.0",
                },
            },
        }
    
    elif method == "notifications/initialized":
        return None  # no response
    
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }
    
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"未知工具: {tool_name}"},
            }
        
        try:
            result_text = handler(arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)},
            }
    
    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"未知方法: {method}"},
        }


# ── 主循环 ────────────────────────────────────────────────────────────────────

def main():
    """MCP Server 主循环：从 stdin 读取 JSON-RPC 请求，输出到 stdout"""
    # 必须用 UTF-8
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            continue
        
        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
