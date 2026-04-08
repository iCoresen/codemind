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

# 停止ARQ Worker
if [ -f logs/arq.pid ]; then
    ARQ_PID=$(cat logs/arq.pid)
    if kill -0 $ARQ_PID 2>/dev/null; then
        kill $ARQ_PID
        echo "✓ 已停止ARQ Worker (PID: $ARQ_PID)"
    else
        echo "ARQ Worker进程已停止"
    fi
    rm -f logs/arq.pid
fi

echo ""
echo "所有服务已停止"
echo "========================================"
