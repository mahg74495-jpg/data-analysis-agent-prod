# Gunicorn 配置文件 — 平板显示良率分析Agent 生产环境
import os

# 绑定地址
bind = "0.0.0.0:5001"

# Worker配置 (ARM64 Mac 16GB)
workers = 1                    # 16GB ARM64 Mac，避免OOM
worker_class = "sync"          # 同步worker，Agent是CPU密集型
threads = 2                    # 每个worker 2个线程
timeout = 300                  # 5分钟超时（大查询需要时间）
graceful_timeout = 30          # 优雅关闭30秒

# 进程管理
max_requests = 50              # 每个worker处理50个请求后重启（防内存泄漏）
max_requests_jitter = 10       # 随机化重启时间
preload_app = False            # macOS fork不安全，禁用预加载

# 日志
accesslog = os.path.expanduser("~/.hermes/logs/daa_access.log")
errorlog = os.path.expanduser("~/.hermes/logs/daa_error.log")
loglevel = "warning"           # 生产环境减少日志噪音

# 进程名
proc_name = "daa-yield-agent"

# Daemon模式（后台运行）
daemon = False                 # launchd管理，不需要daemon

# 安全
limit_request_line = 4096
limit_request_fields = 100
