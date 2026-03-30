# CodeMind MVP (GitHub + Redis Lock + MQ)

这是一个面向“多 Agent 代码审查”的最小可运行骨架，目标是从 pr-agent 中先移植最核心能力：

1. GitHub Webhook 接入（只保留 pull_request 事件）
2. Redis 分布式锁（按 PR 维度防重复并发处理）
3. MQ 队列（基于 Redis Stream）
4. 多 Agent 并发审查骨架（安全/性能/规范）
5. 结果回写 GitHub PR 评论

## 目录结构

- app/main.py: FastAPI 应用入口
- app/github_webhook.py: GitHub Webhook 接收与签名校验
- app/queue.py: Redis Stream 队列封装
- app/lock.py: Redis 分布式锁
- app/worker.py: 队列消费与审查执行
- app/review_agents.py: 多 Agent 审查骨架
- app/github_client.py: GitHub API 读写

## 快速启动

1) 安装依赖

pip install -r requirements.txt

2) 配置环境变量

cp .env.example .env

按需修改：
- GITHUB_WEBHOOK_SECRET
- GITHUB_TOKEN
- REDIS_URL

3) 启动 API

python -m app.main

4) 启动 Worker

python -m app.worker

## GitHub Webhook 配置

在 GitHub 仓库中配置 Webhook：
- Payload URL: http://你的服务地址/api/v1/github/webhook
- Content type: application/json
- Secret: 与 GITHUB_WEBHOOK_SECRET 保持一致
- Events: Pull requests

## 事件处理策略

- 仅处理 pull_request 的 opened/reopened/synchronize
- Webhook 接口只做快速校验和入队，避免超时
- Worker 才执行耗时审查逻辑

## 你接下来可以扩展

1. 将 review_agents.py 中的规则替换为真实 LLM 调用
2. 用 Celery/RabbitMQ/Kafka 替换 Redis Stream
3. 增加仲裁 Agent，对多 Agent 结果进行冲突合并
4. 增加重试、死信队列和监控指标
