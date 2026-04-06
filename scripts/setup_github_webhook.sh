#!/bin/bash

# 自动设置GitHub Webhook脚本

echo "========================================"
echo "GitHub Webhook 自动设置"
echo "========================================"

# 获取ngrok公网URL
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$NGROK_URL" ]; then
    echo "错误: 无法获取ngrok公网URL"
    echo "请先运行 ./scripts/start_all.sh"
    exit 1
fi

WEBHOOK_URL="${NGROK_URL}/api/v1/github/webhook"
echo "Webhook URL: $WEBHOOK_URL"

# 提示用户输入GitHub信息
read -p "请输入GitHub仓库所有者 (owner): " OWNER
read -p "请输入GitHub仓库名称 (repo): " REPO
read -p "请输入GitHub Personal Access Token: " GITHUB_TOKEN

# 检查是否设置了WEBHOOK_SECRET环境变量
if [ -z "$WEBHOOK_SECRET" ]; then
    read -p "请输入Webhook Secret (或留空跳过): " WEBHOOK_SECRET
fi

# 设置Webhook
echo ""
echo "正在设置GitHub Webhook..."

# 构建JSON数据
JSON_DATA="{
    \"name\": \"web\",
    \"active\": true,
    \"events\": [\"pull_request\"],
    \"config\": {
        \"url\": \"$WEBHOOK_URL\",
        \"content_type\": \"json\""

# 如果有secret，添加到配置中
if [ -n "$WEBHOOK_SECRET" ]; then
    JSON_DATA="$JSON_DATA,
        \"secret\": \"$WEBHOOK_SECRET\""
fi

JSON_DATA="$JSON_DATA
    }
}"

# 创建Webhook
RESPONSE=$(curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/$OWNER/$REPO/hooks \
  -d "$JSON_DATA")

# 检查响应
if echo "$RESPONSE" | grep -q '"id"'; then
    echo "✓ GitHub Webhook设置成功！"
    echo ""
    echo "配置详情:"
    echo "- 仓库: $OWNER/$REPO"
    echo "- Webhook URL: $WEBHOOK_URL"
    echo "- 事件: pull_request"
    echo ""
    echo "现在当有新的PR创建或更新时，CodeMind会自动进行代码审查。"
else
    echo "错误: Webhook设置失败"
    echo "响应: $RESPONSE"
fi

echo "========================================"
