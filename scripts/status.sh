#!/bin/bash

# 查看服务状态脚本

echo "========================================"
echo "CodeMind 服务状态"
echo "========================================"

echo "1. Redis状态:"
if redis-cli ping &> /dev/null; then
    echo "   ✓ 运行中"
else
    echo "   ✗ 未运行"
fi

echo ""
echo "2. Celery状态:"
CELERY_PIDS=$(ps aux | grep "celery worker" | grep -v grep | wc -l)
if [ $CELERY_PIDS -gt 0 ]; then
    echo "   ✓ 运行中 ($CELERY_PIDS 个进程)"
    ps aux | grep "celery worker" | grep -v grep | awk '{print "   PID: "$2" - "$11" "$12}'
else
    echo "   ✗ 未运行"
fi

echo ""
echo "3. FastAPI状态:"
if [ -f logs/fastapi.pid ]; then
    FASTAPI_PID=$(cat logs/fastapi.pid)
    if kill -0 $FASTAPI_PID 2>/dev/null; then
        echo "   ✓ 运行中 (PID: $FASTAPI_PID)"
        # 检查API是否可访问
        if curl -s http://localhost:8000/healthz > /dev/null; then
            echo "   API端点: http://localhost:8000"
        else
            echo "   ⚠ API不可访问"
        fi
    else
        echo "   ✗ PID文件存在但进程未运行"
    fi
else
    echo "   ✗ 未运行 (无PID文件)"
fi

echo ""
echo "4. ngrok状态:"
if [ -f logs/ngrok.pid ]; then
    NGROK_PID=$(cat logs/ngrok.pid)
    if kill -0 $NGROK_PID 2>/dev/null; then
        echo "   ✓ 运行中 (PID: $NGROK_PID)"
        # 尝试获取ngrok公网URL
        NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"[^"]*"' | head -1 | cut -d'"' -f4)
        if [ -n "$NGROK_URL" ]; then
            echo "   公网URL: $NGROK_URL"
            echo "   Webhook: $NGROK_URL/api/v1/github/webhook"
        else
            echo "   ⚠ 无法获取公网URL"
        fi
    else
        echo "   ✗ PID文件存在但进程未运行"
    fi
else
    echo "   ✗ 未运行 (无PID文件)"
fi

echo ""
echo "========================================"
echo "日志文件:"
ls -la logs/ 2>/dev/null || echo "logs目录不存在"
echo "========================================"
