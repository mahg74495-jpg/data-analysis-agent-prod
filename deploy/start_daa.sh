#!/bin/bash
# DAA 安全启动脚本 — 先清理旧进程，再启动
# 用于 launchd 调用，解决端口冲突问题

PORT=5001
LOG_DIR="$HOME/.hermes/logs"
mkdir -p "$LOG_DIR"

# 1. 杀掉占用端口的旧进程
OLD_PID=$(lsof -ti :$PORT 2>/dev/null)
if [ -n "$OLD_PID" ]; then
    echo "[$(date)] 清理旧进程: $OLD_PID" >> "$LOG_DIR/daa_startup.log"
    kill $OLD_PID 2>/dev/null
    sleep 2
    # 如果还没死，强制杀
    kill -9 $OLD_PID 2>/dev/null
    sleep 1
fi

# 2. 启动 gunicorn
cd /Users/viton/Data-Analysis-Agent
exec /Users/viton/Data-Analysis-Agent/.venv/bin/gunicorn \
    --config /Users/viton/Data-Analysis-Agent/gunicorn_conf.py \
    wsgi:app
