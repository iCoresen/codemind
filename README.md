# CodeMind

CodeMind 是一个面向 GitHub Pull Request 的自动化代码审查服务，当前仓库版本支持：

1. 拉取 PR 元数据与文件级 Diff
2. 使用 LiteLLM 调用模型进行并发审查
3. 通过 Reducer 汇总审查结果并回写 PR 评论
4. 支持 CLI 手动触发与 GitHub Webhook 触发（ARQ 异步）

## 核心架构

- `app/main.py`：FastAPI 服务入口
- `app/github_webhook.py`：Webhook 接收、签名校验、Redis 去重锁、任务投递
- `app/tasks.py`：ARQ 任务执行异步审查并释放锁
- `app/tools/pr_reviewer.py`：审查主流程（Security/Performance/Style 并发 + Reducer 汇总）
- `app/git_providers/github_provider.py`：GitHub API 访问
- `app/ai_handlers/litellm_ai_handler.py`：LiteLLM 同步/异步调用封装
- `app/algo/pr_processing.py`：Diff 过滤与截断策略
- `app/algo/pr_router.py`：PR 动态分级路由策略
- `app/prompts/*.toml`：各审查 Agent 与 Reducer 的提示词模板

## 分级路由机制 (Routing Tier)

系统内置了根据 PR 具体情况自动或经过用户干预来调度 Agent 执行的路由机制。这会大幅减少无效请求浪费的 Token 和运行时间，避免让大模型审查不必要的内容。调度方式基于以下层级：

- **Level 1（快速通道）**：只运行 `ChangelogAgent`。当系统检测到变更仅包含纯文档或配置文件（如 `.md`, `.json`, `.css`, `.yaml`）时，自动判定为 Level 1。
- **Level 2（日常小改动）**：运行 `ChangelogAgent` + `LogicAgent`。当总变更行数少于 50 行，并且没有触碰核心业务逻辑时，自动采用此层级，跳过深度测试。
- **Level 3（深度审查）**：全量并行运行 `ChangelogAgent` + `LogicAgent` + `UnitTestAgent`。如果检测到代码变动涉及系统核心关键字（如包含 `auth`, `payment`, `database`），则无视行数自动升级到深度审查；或者当文件行数 > 50 所在的重构或重要组件改动。

**如何自定义强制指定 Level？**

你可以跳过自动判断，强制系统按照某个 Level 执行：

- **通过 GitHub 评论指令：**在发起的 PR 内评论 `@codemind`/` /codemind level=1` 等（支持 1, 2, 3）。
- **通过 CLI 参数指令**：运行 CLI 时追加 `--level` 参数，如 `python -m app.cli --pr_url xxx review --level 2`。

## 运行前要求

1. Python 3.11+
2. 可访问 GitHub API
3. 可访问模型服务（默认模型为 `deepseek/deepseek-chat`）
4. 若使用 Webhook，需可用 Redis（用于 ARQ 与去重锁）

## 安装依赖

```bash
python -m pip install -r requirements.txt
```

或使用 Makefile：

```bash
make install
```

## 环境变量

先复制模板：

```bash
cp .env.example .env
```

当前代码实际读取的配置如下：

- `GITHUB_TOKEN`：必填，用于读取 PR 与发布评论
- `AI_API_KEY`：必填，LiteLLM 所用 API Key
- `AI_BASE_URL`：可选，自定义模型网关地址
- `AI_MODEL`：可选，默认 `deepseek/deepseek-chat`
- `AI_FALLBACK_MODELS`：可选，逗号分隔的回退模型列表
- `AI_TIMEOUT`：可选，默认 `60`
- `GITHUB_WEBHOOK_SECRET`：可选，Webhook 签名密钥（为空则跳过校验）
- `REDIS_URL`：可选，默认 `redis://localhost:6379/0`
- `SERVER_HOST`：可选，默认 `0.0.0.0`
- `SERVER_PORT`：可选，默认 `8080`
- `LOG_LEVEL`：可选，默认 `INFO`
- `DEFAULT_REVIEW_LEVEL`：可选，默认 `3`，指定 PR 审查层级（1/2/3）
- `CORE_KEYWORDS`：可选，默认 `auth,payment,database`，核心链路关键字，一旦匹配则强制进入深度审查。

## 方式一：CLI 触发评审

执行：

```bash
python -m app.cli --pr_url https://github.com/<owner>/<repo>/pull/<pr_number> review
```

或：

```bash
make cli
```

说明：`make cli` 仅运行 `python -m app.cli`，需自行补充参数。

预期结果：

- 控制台出现 `Local review execution finished.`
- PR 下出现 `CodeMind PR Review` 评论

兼容性提示：当前 `app/cli.py` 里还保留了旧字段 `DEEPSEEK_API_KEY` 的检查逻辑。若你仅配置了 `AI_API_KEY`，建议同时补一个同值环境变量 `DEEPSEEK_API_KEY` 作为临时兼容。

## 方式二：Webhook + ARQ 异步触发

1. 启动 Redis
2. 启动 ARQ Worker：

```bash
make arq】
```

3. 启动 API：

```bash
python -m app.main
```

或：

```bash
make api
```

4. 健康检查：

```bash
curl http://127.0.0.1:8080/healthz
```

返回：

```json
{"ok": true}
```

5. GitHub Webhook 配置：

- Payload URL：`http://<your-host>:8080/api/v1/github/webhook`
- Content type：`application/json`
- Secret：与 `GITHUB_WEBHOOK_SECRET` 一致
- Event：`Pull requests`

支持动作：

- `opened`
- `reopened`
- `synchronize`

处理链路：Webhook 入站 -> Redis 分布式锁去重 -> ARQ 异步任务 -> 发布评论 -> 释放锁。

## 本地调试 Webhook

若未配置 `GITHUB_WEBHOOK_SECRET`，可本地直接请求：

```bash
curl -X POST "http://127.0.0.1:8080/api/v1/github/webhook" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -d '{
    "action": "opened",
    "repository": {"full_name": "<owner>/<repo>"},
    "pull_request": {"number": <pr_number>, "head": {"sha": "<sha>"}}
  }'
```

## 测试

运行全部单元测试：

```bash
make test
```

或：

```bash
python -m pytest tests/
```

当前测试覆盖重点：

- LiteLLM Handler 的同步/异步调用
- Reviewer 并发调用与汇总格式化
- Webhook 事件提取、去重锁、任务投递
- ARQ 任务执行与异常重试
- PR Diff 处理与截断逻辑

## 常见问题

1. `GITHUB_TOKEN is not set`
   检查 `.env` 是否生效，以及是否在项目根目录启动。

2. GitHub 返回 401/403
   检查 Token 权限是否包含读取 PR 与发布评论。

3. Webhook 返回 `invalid signature`
   检查 GitHub 端 Secret 与 `GITHUB_WEBHOOK_SECRET` 是否一致。

4. Worker 没有处理任务
   检查 Redis 可达、`REDIS_URL` 配置正确，并确认 ARQ Worker 已启动。
