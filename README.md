# CodeMind

CodeMind 是一个最小可运行的 PR 自动审查服务，当前实现包含：

1. GitHub PR 信息与 Diff 拉取
2. 基于 LiteLLM 的模型调用（默认 DeepSeek）
3. 审查结果发布回 PR 评论
4. 两种触发方式：CLI 手动触发、GitHub Webhook 触发

## 当前项目结构（实际可用）

- `app/main.py`：FastAPI 应用入口
- `app/github_webhook.py`：Webhook 接收、签名校验、触发评审
- `app/cli.py`：本地命令行触发评审
- `app/reviewer.py`：PR 评审主流程
- `app/ai_handler.py`：LLM 调用封装（LiteLLM）
- `app/github_client.py`：GitHub API 封装
- `app/prompts/review_prompt.toml`：评审提示词模板

## 运行前要求

1. Python 3.11+（项目读取 TOML 使用 `tomllib`）
2. 可访问 GitHub API
3. 可访问你所使用的模型服务（默认 DeepSeek）

## 环境变量

先复制配置模板：

```bash
cp .env.example .env
```

然后至少填写以下变量：

- `GITHUB_TOKEN`：必填。用于读取 PR 信息与发布评论（建议具备 repo 相关权限）
- `DEEPSEEK_API_KEY`：必填。用于调用模型

可选变量：

- `GITHUB_WEBHOOK_SECRET`：Webhook 签名校验密钥。不填时将跳过签名校验（仅建议本地调试）
- `DEEPSEEK_MODEL`：默认 `deepseek/deepseek-chat`
- `AI_TIMEOUT`：模型调用超时，默认 `60`
- `SERVER_HOST`：默认 `0.0.0.0`
- `SERVER_PORT`：默认 `8080`
- `LOG_LEVEL`：默认 `INFO`

## 安装依赖

```bash
python -m pip install -r requirements.txt
```

或使用 Makefile：

```bash
make install
```

## 运行方式一：CLI 本地触发（推荐先用这个验证）

1. 执行命令：

```bash
python -m app.cli --pr_url https://github.com/<owner>/<repo>/pull/<pr_number> review
```

2. 成功标志：

- 控制台出现 `Local review execution finished.`
- 对应 PR 下新增一条 `CodeMind PR Review` 评论

Makefile 等价命令：

```bash
make cli
```

注意：`make cli` 只会运行 `python -m app.cli`，仍需你手动补全命令参数。

## 运行方式二：Webhook 服务触发

1. 启动 API：

```bash
python -m app.main
```

或：

```bash
make api
```

2. 健康检查：

```bash
curl http://127.0.0.1:8080/healthz
```

期望返回：

```json
{"ok": true}
```

3. 在 GitHub 仓库中配置 Webhook：

- Payload URL: `http://<your-host>:8080/api/v1/github/webhook`
- Content type: `application/json`
- Secret: 与 `GITHUB_WEBHOOK_SECRET` 一致
- Events: 选择 `Pull requests`

4. 触发支持的 PR 事件：

- `opened`
- `reopened`
- `synchronize`

收到上述事件后，服务会直接执行评审并回写评论。

## 本地调试 Webhook（可选）

如果你未设置 `GITHUB_WEBHOOK_SECRET`，可以直接本地模拟请求：

```bash
curl -X POST "http://127.0.0.1:8080/api/v1/github/webhook" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -d '{
	 "action": "opened",
	 "repository": {"full_name": "<owner>/<repo>"},
	 "pull_request": {"number": <pr_number>}
  }'
```

## 常见问题

1. 报错 `GITHUB_TOKEN is not set`：
	检查 `.env` 是否已配置，且启动命令在项目根目录执行。

2. 报错 `DEEPSEEK_API_KEY is not set`：
	检查模型 API Key 是否已配置。

3. 报错 GitHub 401/403：
	检查 `GITHUB_TOKEN` 权限，确保可读取 PR 并可发表评论。

4. Webhook 返回 `invalid signature`：
	检查 GitHub Webhook 的 Secret 与 `.env` 中 `GITHUB_WEBHOOK_SECRET` 是否一致。

## 开发说明

- 入口服务：`python -m app.main`
- CLI 调试：`python -m app.cli --pr_url ... review`
- 评审模板：`app/prompts/review_prompt.toml`

当前版本是单进程、同步执行评审，适合 MVP 验证和小规模使用。
