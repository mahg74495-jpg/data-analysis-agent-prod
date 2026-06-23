# Data Analysis Agent — 离线部署版

## 简介
Data Analysis Agent (DAA) 是一个基于 LLM 的数据分析助手，支持自然语言查询、自动图表生成、仪表盘和报告输出。

## 本地化部署说明
本版本已适配离线/内网环境：
- ✅ 所有 JavaScript 依赖（Plotly.js 等）已本地化
- ✅ 自动更新功能已禁用
- ✅ 支持自定义 LLM API（需配置 LLM/llm_config.json）
- ✅ 数据源支持 DuckDB、CSV、Excel、HTTP API

## 启动方式
```bash
cd /Users/viton/Data-Analysis-Agent
./deploy/start_daa.sh
```
或直接：
```bash
/Users/viton/Data-Analysis-Agent/.venv/bin/gunicorn \
  --config /Users/viton/Data-Analysis-Agent/gunicorn_conf.py \
  wsgi:app
```

访问 http://localhost:5001

## 配置 LLM
编辑 `LLM/llm_config.json`（参考 `LLM/llm_config.example.json`）：
```json
{
  "provider": "deepseek",
  "api_key": "your-api-key",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-v4-pro",
  "enabled": true
}
```

## 数据源
- **DuckDB**：直接连接本地文件
- **CSV/Excel**：上传或指定路径
- **HTTP API**：配置 REST 端点
