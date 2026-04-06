# CodeMind 一键启动脚本

本目录包含用于启动和管理 CodeMind 服务的脚本。

## 脚本说明

### 1. start_all.sh
一键启动所有服务：
- Redis 数据库
- Celery Worker
- FastAPI 应用
- ngrok 内网穿透

### 2. stop_all.sh
停止所有运行中的服务。

### 3. status.sh
查看所有服务的运行状态。

### 4. setup_github_webhook.sh
自动配置 GitHub Webhook。

## 使用方法

### 第一步：安装依赖
```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 ngrok（如果尚未安装）
# 从 https://ngrok.com/download 下载并安装
# 或使用 brew: brew install ngrok/ngrok/ngrok

# 安装 Redis（如果尚未安装）
# macOS: brew install redis
# Ubuntu: sudo apt-get install redis-server
```

### 第二步：设置执行权限
```bash
chmod +x scripts/*.sh
```

### 第三步：配置环境变量
确保你的 `.env` 文件已正确配置，特别是：
- `GITHUB_TOKEN`
- `AI_API_KEY`
- `WEBHOOK_SECRET`

### 第四步：启动服务
```bash
./scripts/start_all.sh
```

### 第五步：设置 GitHub Webhook（可选）
```bash
./scripts/setup_github_webhook.sh
```

### 第六步：查看服务状态
```bash
./scripts/status.sh
```

### 第七步：停止服务
```bash
./scripts/stop_all.sh
```

## 注意事项

1. 确保 ngrok 已正确配置（可能需要注册账号并获取 authtoken）
2. 脚本会创建 `logs/` 目录存放日志文件
3. 所有服务都在后台运行，使用 `stop_all.sh` 可以一键停止
4. 如果需要修改端口，可以在 `start_all.sh` 中调整

## 故障排除

### Redis 无法启动
- 检查 Redis 是否已安装
- 尝试手动启动：`redis-server`

### ngrok 无法连接
- 检查 ngrok 是否已登录：`ngrok config check`
- 获取 authtoken：`ngrok config add-authtoken <your_token>`

### FastAPI 启动失败
- 检查端口 8000 是否被占用
- 查看日志：`tail -f logs/fastapi.log`

### Celery 启动失败
- 检查 Redis 是否运行
- 查看日志：`tail -f logs/celery.log`
