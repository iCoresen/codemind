# CodeMind

CodeMind 是一个面向 GitHub Pull Request 的**智能自动化代码审查服务**，采用分层架构和智能路由机制，为不同复杂度的 PR 提供精准的审查方案。

## ✨ 核心特性

- **智能路由机制**: 根据 PR 特征自动选择审查级别（Level 1-3）
- **多层次审查**: 三种审查深度，对应不同复杂度的代码变更
- **RAG 知识库**: 集成向量检索，基于项目文档提供上下文感知审查
- **优雅降级**: 超时控制和故障恢复机制
- **多语言支持**: 基于 tree-sitter 的多语言 AST 分析
- **容器化部署**: 完整的 Docker + Docker Compose 支持

## 🏗️ 系统架构

### 分层架构设计

```
┌─────────────────────────────────────────────┐
│              API 层 (FastAPI)               │
│  • app/main.py - FastAPI 服务入口           │
│  • app/github_webhook.py - Webhook 接收     │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│           异步任务层 (ARQ + Redis)           │
│  • app/tasks.py - ARQ 异步审查任务          │
│  • app/arq_app.py - ARQ 应用配置            │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│          审查编排层 (PRReviewer)             │
│  • app/tools/pr_reviewer.py - 审查主流程    │
│  • app/reviewers/* - 多层次审查处理器       │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│          算法处理层 (Algorithms)             │
│  • app/algo/pr_router.py - 分级路由         │
│  • app/algo/pr_processing.py - Diff 处理    │
│  • app/algo/ast_analyzer.py - AST 分析      │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│          基础设施层 (Infrastructure)         │
│  • app/git_providers/* - Git 提供者         │
│  • app/ai_handlers/* - AI 模型调用          │
│  • app/rag/* - RAG 知识库系统              │
└─────────────────────────────────────────────┘
```

### 核心组件

#### **审查处理器**
- **ChangelogReviewer** (`app/reviewers/changelog_reviewer.py`): 生成变更日志（轻量级审查）
- **LogicReviewer** (`app/reviewers/logic_reviewer.py`): 逻辑与安全审查（核心审查）
- **UnitTestReviewer** (`app/reviewers/unittest_reviewer.py`): 单元测试建议（深度审查）
- **ResultAggregator** (`app/reviewers/result_aggregator.py`): 审查结果聚合
- **TimeoutController** (`app/reviewers/timeout_controller.py`): 超时控制

#### **RAG 知识库系统**
- **KnowledgeManager** (`app/rag/knowledge_manager.py`): 知识管理
- **VectorStore** (`app/rag/vector_store.py`): ChromaDB 向量存储
- **Retriever** (`app/rag/retriever.py`): 语义检索器
- **EmbeddingService** (`app/rag/embedding_service.py`): 嵌入服务

#### **智能路由系统**
- **PRRouter** (`app/algo/pr_router.py`): 动态路由决策
- **PRProcessing** (`app/algo/pr_processing.py`): Diff 预处理
- **ASTAnalyzer** (`app/algo/ast_analyzer.py`): 代码结构分析

## 🚦 智能路由机制

系统根据 PR 特征自动选择最优审查级别，大幅减少无效请求的 Token 消耗和运行时间。

### 路由决策逻辑

| 级别 | 触发条件 | 审查深度 | 适用场景 |
|------|----------|----------|----------|
| **Level 1** | 仅文档/配置文件变更（`.md`, `.json`, `.yaml`, `.css` 等） | 轻量级 | 文档更新、配置调整 |
| **Level 2** | 变更行数 < 50 且不涉及核心业务逻辑 | 核心审查 | 日常小改动、Bug 修复 |
| **Level 3** | 变更行数 ≥ 50 **或** 涉及核心关键字（`auth`, `payment`, `database` 等） | 深度审查 | 重大重构、核心功能开发 |

### 手动指定级别

跳过自动判断，强制指定审查级别：

- **GitHub 评论指令**: 在 PR 内评论 `@codemind level=1`（支持 1, 2, 3）
- **CLI 参数**: `python -m app.cli --pr_url <url> review --level 2`

### 核心关键字配置
通过环境变量 `CORE_KEYWORDS` 自定义核心业务关键字（默认：`auth,payment,database`）

## 📋 系统要求

### 环境要求
- **Python**: 3.12+（通过 `.python-version` 指定）
- **GitHub API**: 有效的 GitHub Token
- **AI 模型服务**: 支持 LiteLLM 的模型服务（默认 `deepseek/deepseek-chat`）
- **Redis**: Webhook 模式下用于 ARQ 任务队列和分布式锁
- **ChromaDB**: RAG 知识库的向量存储（可选）

### 技术栈
- **后端框架**: FastAPI + Uvicorn
- **异步任务**: ARQ + Redis
- **AI 集成**: LiteLLM（支持多模型代理）
- **向量数据库**: ChromaDB
- **代码分析**: tree-sitter（多语言 AST 解析）
- **依赖管理**: uv（通过 `pyproject.toml` 和 `uv.lock`）
- **测试框架**: pytest + pytest-asyncio

## 🚀 快速开始

### 安装依赖

项目使用 `uv` 进行依赖管理：

```bash
# 使用 uv 安装依赖（推荐）
uv sync

# 或使用 Makefile
make install
```

### 环境配置

1. 复制环境变量模板：
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，配置以下关键变量：

```bash
# GitHub 配置
GITHUB_TOKEN=your_github_personal_access_token

# AI 模型配置
AI_API_KEY=your_ai_api_key
AI_BASE_URL=https://api.deepseek.com  # 可选，自定义网关
AI_MODEL=deepseek/deepseek-chat       # 默认模型
AI_FALLBACK_MODELS=gpt-3.5-turbo,claude-3-haiku  # 回退模型

# 路由配置
DEFAULT_REVIEW_LEVEL=3                # 默认审查级别
CORE_KEYWORDS=auth,payment,database   # 核心业务关键字

# Redis 配置（Webhook 模式必需）
REDIS_URL=redis://localhost:6379/0

# Webhook 安全
GITHUB_WEBHOOK_SECRET=your_webhook_secret
```

## 🐳 Docker 部署

项目提供完整的容器化部署方案：

### 服务架构
- **api**: FastAPI Webhook 接收服务
- **worker**: ARQ 异步任务处理服务  
- **redis**: 任务队列和分布式锁存储

### 部署步骤

1. **准备环境**：
```bash
cp .env.example .env
# 编辑 .env 配置必要的环境变量
```

2. **构建并启动**：
```bash
docker compose up -d --build
```

3. **验证部署**：
```bash
# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f api
docker compose logs -f worker

# 健康检查
curl http://127.0.0.1:8080/healthz
```

4. **停止服务**：
```bash
# 停止容器
docker compose down

# 停止并清理数据卷
docker compose down -v
```





## 🔧 使用方式

### 方式一：CLI 手动触发

```bash
# 基本用法
python -m app.cli --pr_url https://github.com/<owner>/<repo>/pull/<pr_number> review

# 指定审查级别
python -m app.cli --pr_url <url> review --level 2

# 使用 Makefile（需自行补充参数）
make cli
```

**预期结果**：
- 控制台输出：`Local review execution finished.`
- PR 页面出现 `CodeMind PR Review` 评论

### 方式二：Webhook 自动触发

#### 1. 启动服务
```bash
# 启动 Redis
docker run -d -p 6379:6379 redis:alpine

# 启动 ARQ Worker（处理异步任务）
make arq

# 启动 API 服务
make api
```

#### 2. 配置 GitHub Webhook
- **Payload URL**: `http://<your-host>:8080/api/v1/github/webhook`
- **Content type**: `application/json`
- **Secret**: 与 `GITHUB_WEBHOOK_SECRET` 环境变量一致
- **Events**: `Pull requests`（支持 `opened`, `reopened`, `synchronize`）

#### 3. 处理流程
```
Webhook 接收 → Redis 分布式锁去重 → ARQ 异步任务 → 发布评论 → 释放锁
```



### 本地调试 Webhook

未配置 `GITHUB_WEBHOOK_SECRET` 时可直接测试：

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

## 🧪 测试

### 运行测试
```bash
# 运行所有测试
make test

# 或直接使用 pytest
python -m pytest tests/

# 运行特定测试模块
python -m pytest tests/unittest/test_reviewer.py
```

### 测试覆盖范围
- **AI 处理器**: LiteLLM 同步/异步调用测试
- **审查器**: 多层次审查执行与结果聚合
- **Webhook**: 事件处理、去重锁、任务投递
- **异步任务**: ARQ 任务执行与异常重试
- **算法模块**: PR Diff 处理、路由决策、AST 分析
- **RAG 系统**: 向量存储、检索、嵌入服务

## ❓ 常见问题

### 配置问题
**Q: `GITHUB_TOKEN is not set`**
A: 检查 `.env` 文件是否在项目根目录，并确认环境变量已正确加载。

**Q: GitHub API 返回 401/403 错误**
A: 确认 GitHub Token 具有以下权限：`repo`（访问仓库）、`write:discussion`（发布评论）。

**Q: Webhook 返回 `invalid signature`**
A: 确保 GitHub Webhook Secret 与 `GITHUB_WEBHOOK_SECRET` 环境变量完全一致。

### 运行问题
**Q: ARQ Worker 没有处理任务**
A: 检查 Redis 服务是否运行，`REDIS_URL` 配置正确，且 Worker 已成功启动。

**Q: AI 模型调用失败**
A: 验证 `AI_API_KEY` 和 `AI_BASE_URL` 配置，检查网络连接和模型服务状态。

**Q: RAG 知识库无法加载**
A: 确认 ChromaDB 服务可用，向量存储路径有读写权限。

### 性能优化
- **减少 Token 消耗**: 利用智能路由机制，避免不必要的深度审查
- **提高响应速度**: 配置合适的超时时间，合理选择审查级别
- **内存管理**: 监控 Redis 和 ChromaDB 内存使用，适时清理缓存

## 📚 相关文档

- [API 文档](docs/) - 详细 API 接口说明
- [模型配置指南](docs/changing_a_model.md) - 如何更换 AI 模型
- [脚本说明](README_SCRIPTS.md) - 辅助脚本使用指南
- [Makefile 命令](Makefile) - 常用开发命令
