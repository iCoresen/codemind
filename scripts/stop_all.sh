#!/bin/bash

# 停止所有服务脚本

echo "========================================"
echo "停止所有CodeMind服务"
echo "========================================"

# 停止FastAPI
if [ -f logs/fastapi.pid ]; then
    FASTAPI_PID=$(cat logs/fastapi.pid)
    if kill -0 $FASTAPI_PID 2>/dev/null; then
        kill $FASTAPI_PID
        echo "✓ 已停止FastAPI (PID: $FASTAPI_PID)"
    else
        echo "FastAPI进程已停止"
    fi
    rm -f logs/fastapi.pid
fi

# 停止ngrok
if [ -f logs/ngrok.pid ]; then
    NGROK_PID=$(cat logs/ngrok.pid)
    if kill -0 $NGROK_PID 2>/dev/null; then
        kill $NGROK_PID
        echo "✓ 已停止ngrok (PID: $NGROK_PID)"
    else
        echo "ngrok进程已停止"
    fi
    rm -f logs/ngrok.pid
fi

# 停止Celery Worker
CELERY_PIDS=$(ps aux | grep "celery worker" | grep -v grep | awk '{print $2}')
if [ -n "$CELERY_PIDS" ]; then
    echo "$CELERY_PIDS" | xargs kill -9
    echo "✓ 已停止所有Celery Worker进程"
fi

echo ""
echo "所有服务已停止"
echo "========================================"
