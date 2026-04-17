"""
RAG 集成测试脚本 - 使用真实数据验证检索质量

测试策略：
1. 用当前仓库的文档测试 docs 检索
2. 用当前仓库的 git 历史测试 commits 检索
3. 使用 ground truth 验证 hit rate 和 MRR

运行方式：
    cd /home/xps/codehub/codemind/codemind
    python -m pytest tests/test_rag_integration.py -v -s

或直接运行：
    python tests/test_rag_integration.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# 确保项目根目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag.vector_store import ChromaVectorStore
from app.rag.embedding_service import EmbeddingService
from app.rag.document_parser import DocumentParser
from app.rag.knowledge_manager import KnowledgeManager
from app.rag.data_collector import GitHubDataCollector
from app.rag.retriever import RAGRetriever
from app.rag.evaluation import RAGEvaluator
from app.config import Settings
from app.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from app.git_providers.github_provider import GitHubProvider

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("test_rag_integration")

# 测试配置
TEST_DATA_DIR = "./data/test_rag_integration"
README_PATH = "./README.md"
DOCS_DIR = "./docs"


class RAGIntegrationTester:
    """RAG 集成测试"""

    def __init__(self):
        self.settings = None
        self.vector_store = None
        self.embedding_service = None
        self.document_parser = None
        self.knowledge_manager = None
        self.github_provider = None
        self.github_collector = None
        self.retriever = None
        self.evaluator = None

    def setup(self):
        """初始化所有组件"""
        logger.info("=" * 60)
        logger.info("初始化 RAG 组件...")
        logger.info("=" * 60)

        # 加载配置
        self.settings = Settings(
            github_token=os.getenv("GITHUB_TOKEN", ""),
            ai_api_key=os.getenv("AI_API_KEY", ""),
            ai_base_url=os.getenv("AI_BASE_URL", ""),
            ai_model=os.getenv("AI_MODEL", "deepseek/deepseek-chat"),
            ai_embedding_model="text-embedding-3-small",
            ai_embedding_api_key=os.getenv("EMBEDDING_API_KEY", ""),
            ai_embedding_base_url=os.getenv("EMBEDDING_BASE_URL", ""),
            ai_fallback_models=os.getenv("AI_FALLBACK_MODELS", ""),
            ai_timeout=60,
            github_webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET", ""),
            server_host="0.0.0.0",
            server_port=8080,
            log_level="INFO",
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            changelog_soft_timeout=5.0,
            changelog_hard_timeout=10.0,
            logic_soft_timeout=45.0,
            logic_hard_timeout=90.0,
            unittest_soft_timeout=45.0,
            unittest_hard_timeout=90.0,
            default_review_level=3,
            core_keywords=["auth", "payment", "database"],
        )

        # 初始化向量存储 (使用独立的测试目录)
        self.vector_store = ChromaVectorStore(
            persist_directory=f"{TEST_DATA_DIR}/chroma"
        )

        # 初始化 AI Handler
        ai_handler = LiteLLMAIHandler(self.settings)

        # 初始化 Embedding 服务
        self.embedding_service = EmbeddingService(ai_handler, self.settings)

        # 初始化文档解析器
        self.document_parser = DocumentParser(chunk_size=500, chunk_overlap=50)

        # 初始化 Knowledge Manager
        self.knowledge_manager = KnowledgeManager(
            vector_store=self.vector_store,
            embedding_service=self.embedding_service,
            document_parser=self.document_parser
        )

        # 初始化 GitHub Provider
        self.github_provider = GitHubProvider(self.settings)

        # 初始化 GitHub Data Collector
        self.github_collector = GitHubDataCollector(
            github_provider=self.github_provider,
            embedding_service=self.embedding_service,
            vector_store=self.vector_store
        )

        # 初始化 Retriever
        self.retriever = RAGRetriever(
            vector_store=self.vector_store,
            embedding_service=self.embedding_service
        )

        # 初始化 Evaluator
        self.evaluator = RAGEvaluator()

        logger.info("组件初始化完成")

    async def clear_collections(self):
        """清空 collections（测试前重置状态）"""
        logger.info("清空现有 collections...")
        try:
            self.vector_store.client.delete_collection(name="docs")
            self.vector_store.client.delete_collection(name="commits")
            # 重新创建
            self.vector_store.collection = self.vector_store.client.get_or_create_collection(
                name="commits",
                metadata={"hnsw:space": "cosine"}
            )
            self.vector_store.docs_collection = self.vector_store.client.get_or_create_collection(
                name="docs",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("Collections 已重置")
        except Exception as e:
            logger.warning(f"清空 collections 时出错 (可能为空): {e}")

    async def ingest_documents(self):
        """Ingest 测试文档"""
        logger.info("=" * 60)
        logger.info("开始 Ingest 文档...")
        logger.info("=" * 60)

        docs_to_ingest = []

        # README.md
        if os.path.exists(README_PATH):
            docs_to_ingest.append(README_PATH)
            logger.info(f"  + {README_PATH}")
        else:
            logger.warning(f"  ! {README_PATH} 不存在，跳过")

        # docs/ 目录下的所有 .md 文件
        if os.path.exists(DOCS_DIR):
            for md_file in Path(DOCS_DIR).glob("*.md"):
                docs_to_ingest.append(str(md_file))
                logger.info(f"  + {md_file}")
        else:
            logger.warning(f"  ! {DOCS_DIR} 目录不存在，跳过")

        if not docs_to_ingest:
            logger.error("没有找到任何文档！")
            return

        logger.info(f"\n共找到 {len(docs_to_ingest)} 个文档，开始 ingest...")

        for doc_path in docs_to_ingest:
            try:
                await self.knowledge_manager.ingest_document(doc_path)
                logger.info(f"  ✓ {doc_path}")
            except Exception as e:
                logger.error(f"  ✗ {doc_path}: {e}")

        logger.info("文档 ingest 完成")

    async def build_bm25_index(self):
        """构建 BM25 索引"""
        logger.info("=" * 60)
        logger.info("构建 BM25 索引...")
        logger.info("=" * 60)

        docs = self.knowledge_manager.load_all_docs_for_bm25()
        logger.info(f"从 ChromaDB 加载了 {len(docs)} 个文档 chunks")

        if docs:
            self.retriever.build_bm25_index(docs)
            logger.info("BM25 索引构建完成")
        else:
            logger.warning("没有文档可用于构建 BM25 索引")

        return docs

    async def collect_commits(self, owner: str, repo: str, days: int = 90):
        """收集 Git 提交历史"""
        logger.info("=" * 60)
        logger.info(f"收集 {owner}/{repo} 近 {days} 天的 commits...")
        logger.info("=" * 60)

        try:
            # 将天数转换为 ISO 格式日期字符串
            since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
            logger.info(f"since 参数: {since_date}")

            count = await self.github_collector.collect_and_store_commits(
                owner=owner,
                repo=repo,
                since=since_date
            )
            logger.info(f"成功收集 {count} 条 commits")
        except Exception as e:
            logger.error(f"收集 commits 失败: {e}")
            logger.warning("Commits 检索测试将被跳过")

    async def test_docs_retrieval(self):
        """测试文档检索"""
        logger.info("=" * 60)
        logger.info("测试文档检索...")
        logger.info("=" * 60)

        # Ground truth 测试用例
        # query: 查询文本
        # expected_sources: 期望返回的文档来源 (metadata 中的 source 字段)
        test_cases = [
            {
                "query": "what is the system architecture?",
                "expected_sources": ["README.md"],
                "description": "查询系统架构"
            },
            {
                "query": "how does the review process work?",
                "expected_sources": ["README.md"],
                "description": "查询审查流程"
            },
            {
                "query": "what AI models are supported?",
                "expected_sources": ["changing_a_model.md", "README.md"],
                "description": "查询支持的 AI 模型"
            },
            {
                "query": "how to change the AI model?",
                "expected_sources": ["changing_a_model.md"],
                "description": "查询如何切换模型"
            },
            {
                "query": "what programming languages are supported?",
                "expected_sources": ["README.md"],
                "description": "查询支持的编程语言"
            },
            {
                "query": "is docker supported?",
                "expected_sources": ["README.md"],
                "description": "查询 Docker 支持"
            },
        ]

        results = []

        for i, case in enumerate(test_cases, 1):
            logger.info(f"\n[Test {i}] {case['description']}")
            logger.info(f"  Query: \"{case['query']}\"")
            logger.info(f"  Expected: {case['expected_sources']}")

            retrieved = await self.retriever.hybrid_search_docs(
                case["query"],
                top_k=5
            )

            if not retrieved:
                logger.warning("  结果: 无")
                results.append({
                    **case,
                    "retrieved": [],
                    "hit": False,
                    "hit_rate": 0.0
                })
                continue

            # 检查是否命中期望的文档
            retrieved_sources = [
                r.get("metadata", {}).get("source", "")
                for r in retrieved
            ]
            hits = [
                src for src in retrieved_sources
                if src in case["expected_sources"]
            ]
            hit_rate = len(hits) / len(case["expected_sources"]) if case["expected_sources"] else 0

            logger.info(f"  Retrieved sources: {retrieved_sources}")
            logger.info(f"  Hits: {hits}")
            logger.info(f"  Hit Rate: {hit_rate:.2%}")

            # 打印前 3 个结果
            for j, doc in enumerate(retrieved[:3], 1):
                source = doc.get("metadata", {}).get("source", "unknown")
                text_preview = doc.get("document", "")[:80].replace("\n", " ")
                logger.info(f"    [{j}] {source}: {text_preview}...")

            results.append({
                **case,
                "retrieved": retrieved_sources,
                "hit": hit_rate > 0,
                "hit_rate": hit_rate
            })

            # 记录到 evaluator
            self.evaluator.evaluate_retrieval(
                query=case["query"],
                retrieved_docs=retrieved_sources,
                ground_truth_docs=case["expected_sources"],
                context_relevance=hit_rate
            )

        # 汇总
        logger.info("\n" + "=" * 60)
        logger.info("文档检索测试汇总")
        logger.info("=" * 60)

        hit_count = sum(1 for r in results if r["hit"])
        avg_hit_rate = sum(r["hit_rate"] for r in results) / len(results) if results else 0

        logger.info(f"总测试用例: {len(results)}")
        logger.info(f"命中数量: {hit_count}")
        logger.info(f"平均 Hit Rate: {avg_hit_rate:.2%}")

        for r in results:
            status = "✓" if r["hit"] else "✗"
            logger.info(f"  {status} {r['description']}: {r['hit_rate']:.2%}")

        return results

    async def test_commits_retrieval(self, owner: str, repo: str):
        """测试提交检索"""
        logger.info("=" * 60)
        logger.info(f"测试 Commits 检索 ({owner}/{repo})...")
        logger.info("=" * 60)

        # 基于代码中的实际 commit 主题设计的测试
        test_cases = [
            {
                "query": "RAG embedding vector retrieval",
                "description": "查询 RAG 相关 commits"
            },
            {
                "query": "configuration settings loading cache",
                "description": "查询配置重构相关 commits"
            },
            {
                "query": "agent reviewer rename refactor",
                "description": "查询代码重构相关 commits"
            },
        ]

        for i, case in enumerate(test_cases, 1):
            logger.info(f"\n[Test {i}] {case['description']}")
            logger.info(f"  Query: \"{case['query']}\"")

            retrieved = await self.retriever.get_relevant_commits(
                query=case["query"],
                owner=owner,
                repo=repo,
                top_k=5
            )

            if not retrieved:
                logger.warning("  结果: 无")
                continue

            logger.info(f"  找到 {len(retrieved)} 条相关 commits:")
            for j, commit in enumerate(retrieved[:5], 1):
                msg = commit.get("document", "")[:60].replace("\n", " ")
                dist = commit.get("distance", 0)
                logger.info(f"    [{j}] dist={dist:.4f}: {msg}...")

    async def run_all_tests(self, owner: str = "Coresen", repo: str = "codemind"):
        """运行所有测试"""
        logger.info("\n" + "=" * 60)
        logger.info("RAG 集成测试开始")
        logger.info("=" * 60)
        logger.info(f"测试仓库: {owner}/{repo}")
        logger.info(f"Chroma 目录: {TEST_DATA_DIR}/chroma")

        # 初始化
        self.setup()

        # 清空旧数据
        await self.clear_collections()

        # Ingest 文档
        await self.ingest_documents()

        # 构建 BM25 索引
        await self.build_bm25_index()

        # 收集 commits (如果配置了 GITHUB_TOKEN)
        if os.getenv("GITHUB_TOKEN"):
            await self.collect_commits(owner, repo, days=90)
        else:
            logger.warning("=" * 60)
            logger.warning("未配置 GITHUB_TOKEN，跳过 commits 收集")
            logger.warning("如需测试 commits 检索，请设置 GITHUB_TOKEN 环境变量")
            logger.warning("=" * 60)

        # 测试文档检索
        await self.test_docs_retrieval()

        # 测试 commits 检索
        if os.getenv("GITHUB_TOKEN"):
            await self.test_commits_retrieval(owner, repo)
        else:
            logger.info("\n跳过 commits 检索测试 (需要 GITHUB_TOKEN)")

        # 最终报告
        logger.info("\n" + "=" * 60)
        logger.info("测试完成!")
        logger.info("=" * 60)

        # 计算最终指标
        metrics = self.evaluator.calculate_average_metrics()
        logger.info(f"平均 Relevance Score: {metrics.get('avg_relevance', 0):.2%}")
        logger.info(f"平均 Hit Rate: {metrics.get('avg_hit_rate', 0):.2%}")

        # 清理
        logger.info("\n提示: 测试数据保留在 %s", f"{TEST_DATA_DIR}/chroma")
        logger.info("如需清理，运行: rm -rf %s", f"{TEST_DATA_DIR}")


async def main():
    """主入口"""
    tester = RAGIntegrationTester()

    # 可以通过环境变量指定测试的仓库
    owner = os.getenv("TEST_GITHUB_OWNER", "Coresen")
    repo = os.getenv("TEST_GITHUB_REPO", "codemind")

    await tester.run_all_tests(owner=owner, repo=repo)


if __name__ == "__main__":
    asyncio.run(main())


# pytest 兼容的测试函数
@pytest.mark.asyncio
async def test_rag_full_integration():
    """完整的 RAG 集成测试 (供 pytest 调用)"""
    tester = RAGIntegrationTester()
    owner = os.getenv("TEST_GITHUB_OWNER", "Coresen")
    repo = os.getenv("TEST_GITHUB_REPO", "codemind")
    await tester.run_all_tests(owner=owner, repo=repo)
