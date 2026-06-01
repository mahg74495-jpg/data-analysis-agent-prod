# 平板显示良率分析系统 — 生产部署

基于 [Zafer-Liu/Data-Analysis-Agent](https://github.com/Zafer-Liu/Data-Analysis-Agent) 的平板显示制造行业定制版本。

## 新增内容

| 文件 | 说明 |
|------|------|
| `gunicorn_conf.py` | Gunicorn 生产配置（3 worker, 自动重启, 防泄漏） |
| `generate_10m_fpd.py` | 1000万行平板显示数据生成脚本 |
| `import_to_sqlite.py` | CSV → SQLite 高效导入（32万行/秒） |
| `run_analysis_10m_v3.py` | 5维度自动分析脚本（通过DAA API） |
| `analysis_output_10m/` | 分析结果（Markdown报告） |
| `deploy/com.viton.daa-yield-agent.plist` | macOS launchd 服务配置 |

## 快速部署

```bash
# 1. 安装依赖
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 生成数据（可选）
python generate_10m_fpd.py

# 3. 导入SQLite
python import_to_sqlite.py

# 4. 生产启动
gunicorn --config gunicorn_conf.py api:create_app\(\)

# 5. 设置开机自启（macOS）
cp deploy/com.viton.daa-yield-agent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.viton.daa-yield-agent.plist
```

## 性能数据

- 数据规模：1000万行 × 20列
- 数据库：SQLite 2.1GB（含索引）
- 导入速度：32万行/秒
- 查询速度：聚合查询 <5秒，相关性分析 <10秒
