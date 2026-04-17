# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

```bash
# 安装依赖（使用 uv）
uv sync

# 运行 API 服务（FastAPI + Webhook）
make api

# 运行 CLI 手动触发 PR 审查
python -m app.cli --pr_url https://github.com/<owner>/<repo>/pull/<pr_number> review --level <1|2|3>

# 运行 ARQ Worker（处理异步审查任务）
arq -A app.arq_app worker --loglevel=info

# 运行所有测试
make test

# 运行单个测试
python -m pytest tests/unittest/test_reviewer.py

# RAG 集成测试
python -m pytest tests/test_rag_integration.py -v -s
```

## 架构概览

CodeMind 是一个面向 GitHub PR 的智能代码审查服务，采用分层架构：

### 分层结构
```
API 层 (FastAPI) → 异步任务层 (ARQ + Redis) → 审查编排层 (PRReviewer) → 算法处理层 → 基础设施层
```

### 核心流程
1. **触发方式**：CLI 手动或 GitHub Webhook 自动
2. **路由决策** (`app/algo/pr_router.py`)：根据 PR 特征自动选择 Level 1/2/3
3. **审查执行**：
   - **Level 1** (ChangelogReviewer)：文档变更检查
   - **Level 2** (+LogicReviewer)：逻辑与安全审查
   - **Level 3** (+UnitTestReviewer)：深度审查+测试建议
4. **结果聚合** (ResultAggregator)：合并多级审查结果并发布到 PR

### 关键组件
- `app/tools/pr_reviewer.py`：审查主流程编排
- `app/reviewers/`：三层审查器实现
- `app/rag/`：RAG 知识库（ChromaDB + BM25 混合检索）
- `app/ai_handlers/litellm_ai_handler.py`：统一 AI 模型接口

### 配置
- 环境变量通过 `app/config.py` 的 `load_settings()` 加载（带全局缓存）
- 关键配置：`GITHUB_TOKEN`、`AI_API_KEY`、`AI_BASE_URL`、`REDIS_URL`
- 路由关键字：`CORE_KEYWORDS`（默认：auth,payment,database）

### Docker 部署
```bash
docker compose up -d --build  # 启动全部服务（api + worker + redis）
```
