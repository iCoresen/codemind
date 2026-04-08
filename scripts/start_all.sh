#!/bin/bash

# 一键启动脚本 - 启动所有CodeMind服务并配置ngrok内网穿透

set -e  # 遇到错误时退出

echo "========================================"
echo "CodeMind 一键启动脚本"
echo "========================================"

# 检查必要的命令是否存在
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo "错误: 未找到 $1 命令"
        echo "请先安装: $2"
        exit 1
    fi
}

echo "检查依赖..."
check_command "uv" "uv (从 https://github.com/astral-sh/uv 安装)"
check_command "ngrok" "ngrok (从 https://ngrok.com/download 下载)"
check_command "redis-cli" "Redis (brew install redis 或 apt-get install redis)"

# 检查Redis是否运行
if ! redis-cli ping &> /dev/null; then
    echo "警告: Redis服务未运行"
    echo "尝试启动Redis..."
    
    # 尝试不同的启动方式
    if command -v brew &> /dev/null; then
        brew services start redis
    elif command -v systemctl &> /dev/null; then
        sudo systemctl start redis
    elif command -v service &> /dev/null; then
        sudo service redis start
    else
        echo "请手动启动Redis服务: redis-server"
        exit 1
    fi
    
    # 等待Redis启动
    sleep 3
    if ! redis-cli ping &> /dev/null; then
        echo "错误: Redis启动失败，请手动启动"
        exit 1
    fi
fi

echo "✓ 所有依赖检查通过"

# 设置环境变量
export PYTHONPATH=$(pwd)
echo "设置PYTHONPATH: $PYTHONPATH"

# 创建日志目录
mkdir -p logs

echo ""
echo "1. 启动ARQ Worker..."
# 应用内部已配置将日志定性输出到 logs/arq.log，这里将 stdout/stderr 写入 logs/arq_stdout.log 避免日志重复
nohup uv run arq app.arq_app.WorkerSettings > logs/arq_stdout.log 2>&1 &
ARQ_PID=$!
echo "✓ ARQ Worker已启动 (PID: $ARQ_PID)"
echo $ARQ_PID > logs/arq.pid

echo ""
echo "2. 启动FastAPI应用..."
# 应用内部已配置将日志定性输出到 logs/fastapi.log，这里将 stdout/stderr 写入 logs/fastapi_stdout.log 避免日志重复
nohup uv run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --access-log > logs/fastapi_stdout.log 2>&1 &
FASTAPI_PID=$!
echo "✓ FastAPI应用已启动 (PID: $FASTAPI_PID)"
echo $FASTAPI_PID > logs/fastapi.pid

# 等待FastAPI启动
echo "等待FastAPI启动..."
sleep 5

# 检查FastAPI是否运行
if ! curl -s http://localhost:8000/healthz > /dev/null; then
    echo "错误: FastAPI启动失败"
    exit 1
fi

echo "✓ FastAPI运行正常"

echo ""
echo "3. 启动ngrok内网穿透..."
# 启动ngrok，将本地8000端口暴露到公网
nohup ngrok http 8000 --log=stdout > logs/ngrok.log 2>&1 &
NGROK_PID=$!
echo "✓ ngrok已启动 (PID: $NGROK_PID)"
echo $NGROK_PID > logs/ngrok.pid

# 等待ngrok启动并获取公网URL
echo "等待ngrok启动..."
sleep 8

# 从ngrok日志中提取公网URL
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o '"public_url":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$NGROK_URL" ]; then
    echo "警告: 无法获取ngrok公网URL，请检查ngrok.log"
    NGROK_URL="请手动检查ngrok状态"
else
    echo "✓ ngrok公网URL: $NGROK_URL"
fi

echo ""
echo "========================================"
echo "所有服务已启动完成！"
echo "========================================"
echo ""
echo "服务状态:"
echo "1. Redis:      ✓ 运行中"
echo "2. ARQ:     ✓ 运行中 (查看日志: tail -f logs/arq.log)"
echo "3. FastAPI:    ✓ 运行中 (PID: $FASTAPI_PID)"
echo "4. ngrok:      ✓ 运行中 (PID: $NGROK_PID)"
echo ""
echo "Webhook端点:"
echo "- 本地地址:    http://localhost:8000/api/v1/github/webhook"
echo "- 公网地址:    $NGROK_URL/api/v1/github/webhook"
echo ""
echo "健康检查:"
echo "- 本地: curl http://localhost:8000/healthz"
echo "- 公网: curl $NGROK_URL/healthz"
echo ""
echo "日志文件:"
echo "- ARQ日志:  logs/arq.log      (任务运行日志)"
echo "- FastAPI日志: logs/fastapi.log     (Web请求与路由日志)"
echo "- ngrok日志:   logs/ngrok.log"
echo "- 控制台输出:  logs/arq_stdout.log, logs/fastapi_stdout.log (崩溃或标准输出)"
echo ""
echo "停止所有服务: ./scripts/stop_all.sh"
echo "========================================"

# 保存PID到文件，供停止脚本使用
echo "$FASTAPI_PID" > logs/fastapi.pid
echo "$NGROK_PID" > logs/ngrok.pid

# 显示ngrok日志的最后几行
echo ""
echo "ngrok状态:"
tail -5 logs/ngrok.log
