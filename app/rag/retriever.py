import logging
from typing import List, Dict, Any
from rank_bm25 import BM25Okapi

from app.rag.vector_store import ChromaVectorStore
from app.rag.embedding_service import EmbeddingService

logger = logging.getLogger("codemind.rag.retriever")


class RAGRetriever:
    """
    混合检索器 (Hybrid Retriever)
    
    结合两种检索算法的优势：
    1. 向量检索 (Vector Search)：基于语义相似度，适合理解用户意图
    2. BM25 检索 (Keyword Search)：基于词项频率，适合精确关键词匹配
    
    融合策略：RRF (Reciprocal Rank Fusion) 倒数排名融合算法
    
    使用场景：
    - 文档检索 (hybrid_search_docs)
    - 提交记录检索 (get_relevant_commits)
    """
    
    def __init__(
        self,
        vector_store: ChromaVectorStore,
        embedding_service: EmbeddingService
    ):
        """
        初始化混合检索器
        
        Args:
            vector_store: Chroma 向量数据库实例，负责向量存储和查询
            embedding_service: 嵌入服务，将文本转换为向量表示
        """
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        # BM25 语料库缓存：key=doc_id, value=分词后的 token 列表
        # 用于快速重建 BM25 索引
        self._bm25_corpus = {}
        
    def build_bm25_index(self, docs: List[Dict[str, Any]]) -> None:
        """
        构建 BM25 倒排索引
        
        BM25 是一种基于词项频率的信息检索算法，考虑了：
        - 词项在文档中的出现频率 (TF)
        - 词项的文档频率，区分常见词和稀有词 (IDF)
        - 文档长度归一化
        
        Args:
            docs: 文档列表，每个文档必须包含 'text' 字段
                  示例: [{"id": "1", "text": "hello world"}, ...]
        """
        # 1. 文本预处理：转小写 + 分词
        #    输入: [{"text": "Hello World"}]
        #    输出: [["hello", "world"]]
        corpus = [doc['text'].lower().split() for doc in docs]
        
        # 2. 构建 BM25 索引
        #    BM25Okapi 是 BM25 的标准实现变体
        self.bm25 = BM25Okapi(corpus)
        
        # 3. 保存文档引用，用于后续结果映射
        #    BM25 只返回索引位置，需要这个来获取原始文档
        self._bm25_docs = docs

    async def hybrid_search_docs(
        self, 
        query: str, 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        混合搜索：同时使用向量检索和 BM25 检索，结果通过 RRF 融合
        
        算法流程：
        ┌─────────────────────────────────────────────────────────────┐
        │  输入: 用户查询 "如何实现用户认证"                            │
        │                                                             │
        │  ┌──────────────────┐     ┌──────────────────┐             │
        │  │   向量检索        │     │   BM25 检索       │             │
        │  │   (语义理解)       │     │   (关键词匹配)    │             │
        │  │                   │     │                   │             │
        │  │  1. 查询文本 → 向量 │     │  1. 查询 → tokens │             │
        │  │  2. 相似度搜索     │     │  2. 词项评分      │             │
        │  │  3. 返回 Top 2K   │     │  3. 返回 Top 2K   │             │
        │  └────────┬─────────┘     └────────┬─────────┘             │
        │           │                        │                        │
        │           ▼                        ▼                        │
        │  ┌────────────────────────────────────────────┐             │
        │  │          RRF 融合 (Reciprocal Rank Fusion) │             │
        │  │                                            │             │
        │  │  score(doc) = Σ 1/(k + rank_i(doc))        │             │
        │  │                  ↑                          │             │
        │  │           各检索算法的排名                  │             │
        │  └────────────────────┬───────────────────────┘             │
        │                       │                                     │
        │                       ▼                                     │
        │               输出: Top-K 融合结果                           │
        └─────────────────────────────────────────────────────────────┘
        
        Args:
            query: 用户查询文本
            top_k: 返回的最终结果数量（融合后）
            
        Returns:
            文档列表，按融合分数降序排列
            每个文档包含: id, document, metadata
        """
        # 空查询直接返回空结果
        if not query:
            return []
            
        try:
            # ============================================================
            # 第一步：向量检索 (Vector Search)
            # ============================================================
            
            # 1.1 将用户查询转换为向量表示
            #     输入: "如何实现用户认证"
            #     输出: [0.123, -0.456, 0.789, ...] (1536 维向量)
            query_embedding = (
                await self.embedding_service.get_embeddings([query])
            )[0]
            
            # 1.2 在文档向量库中搜索相似文档
            #     n_results=2*top_k: 获取更多候选结果，给融合算法更多选择
            vector_results = self.vector_store.query_docs(
                query_embeddings=[query_embedding],
                n_results=top_k * 2  # 2x 候选，留给融合
            )
            
            # 1.3 整理向量搜索结果，计算相似度分数
            #     Chroma 返回的是"距离"（越小越相似），需转换为"相似度"
            #     转换公式: similarity = 1 / (1 + distance)
            #     距离 0 → 相似度 1.0
            #     距离 1 → 相似度 0.5
            #     距离 2 → 相似度 0.33
            vector_scored_docs = {}
            if vector_results["documents"] and vector_results["documents"][0]:
                for i in range(len(vector_results["documents"][0])):
                    doc_id = vector_results["ids"][0][i]
                    # 距离转相似度
                    vector_score = 1.0 / (1.0 + vector_results["distances"][0][i])
                    vector_scored_docs[doc_id] = {
                        "id": doc_id,
                        "document": vector_results["documents"][0][i],
                        "metadata": vector_results["metadatas"][0][i],
                        "vector_score": vector_score
                    }
                    
            # ============================================================
            # 第二步：BM25 关键词检索
            # ============================================================
            
            bm25_scored_docs = {}
            # 检查是否已构建 BM25 索引
            # 如果没有构建，则跳过 BM25 搜索（向量搜索仍有效）
            if hasattr(self, 'bm25'):
                # 2.1 查询预处理：转小写 + 分词
                #     "How to implement auth" → ["how", "to", "implement", "auth"]
                tokenized_query = query.lower().split()
                
                # 2.2 计算每个文档与查询的相关性分数
                #     返回与查询等长的数组，每项是对应文档的 BM25 分数
                doc_scores = self.bm25.get_scores(tokenized_query)
                
                # 2.3 获取分数最高的文档索引
                #     range(len(doc_scores)): [0, 1, 2, ..., n-1]
                #     按分数排序（降序），取前 2K 个
                top_n = sorted(
                    range(len(doc_scores)), 
                    key=lambda i: doc_scores[i], 
                    reverse=True
                )[:top_k * 2]
                
                # 2.4 整理 BM25 结果
                for idx in top_n:
                    # 分数 > 0 表示至少有一个查询词在文档中出现
                    if doc_scores[idx] > 0:
                        doc = self._bm25_docs[idx]
                        doc_id = doc["id"]
                        bm25_scored_docs[doc_id] = {
                            "id": doc_id,
                            "document": doc["text"],
                            "metadata": doc["metadata"],
                            "bm25_score": doc_scores[idx]
                        }
            
            # ============================================================
            # 第三步：RRF 融合 (Reciprocal Rank Fusion)
            # ============================================================
            
            # RRF 公式: score(d) = Σ 1 / (k + rank_i(d))
            # 
            # k: RRF 常量，通常设为 60
            # - k 越大，各排名之间的差异影响越小
            # - k=0 时退化为只看排名
            # - k=60 是实践中的经验值
            #
            # 优势：
            # - 简单，无需调参
            # - 平衡两种搜索结果
            # - 对排名位置敏感，对绝对分数不敏感
            fused_scores: Dict[str, Dict[str, Any]] = {}
            k = 60  # RRF 常量
            
            # 3.1 融合向量搜索结果
            #     按相似度降序排列，向量搜索得分高的排在前面
            vector_ranked = sorted(
                vector_scored_docs.values(), 
                key=lambda x: x["vector_score"], 
                reverse=True
            )
            for rank, doc in enumerate(vector_ranked):
                doc_id = doc["id"]
                # 首次遇到该文档时初始化
                if doc_id not in fused_scores:
                    fused_scores[doc_id] = {"doc": doc, "score": 0.0}
                # 累加 RRF 分数：排名越靠前，加分越多
                # rank=0 → 1/(60+0) ≈ 0.0164
                # rank=5 → 1/(60+5) ≈ 0.0154
                fused_scores[doc_id]["score"] += 1.0 / (k + rank + 1)
                
            # 3.2 融合 BM25 搜索结果
            #     同样按分数降序排列
            bm25_ranked = sorted(
                bm25_scored_docs.values(), 
                key=lambda x: x["bm25_score"], 
                reverse=True
            )
            for rank, doc in enumerate(bm25_ranked):
                doc_id = doc["id"]
                if doc_id not in fused_scores:
                    fused_scores[doc_id] = {"doc": doc, "score": 0.0}
                fused_scores[doc_id]["score"] += 1.0 / (k + rank + 1)
            
            # 3.3 按融合分数排序，返回 Top-K
            #     注意：可能返回的文档同时来自向量和 BM25
            sorted_fused = sorted(
                fused_scores.values(), 
                key=lambda x: x["score"], 
                reverse=True
            )
            return [item["doc"] for item in sorted_fused[:top_k]]
            
        except Exception as e:
            # 异常处理：记录错误并返回空列表
            # 确保单个检索错误不会影响整个系统
            logger.error(f"Hybrid search failed: {e}")
            return []

    async def get_relevant_commits(
        self, 
        query: str, 
        owner: str, 
        repo: str, 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        获取与查询相关的提交记录（专用于 Git 提交）
        
        与 hybrid_search_docs 的区别：
        - 仅检索 "commits" 集合（而非 "docs" 集合）
        - 过滤条件：限定特定仓库 (owner/repo)
        - 仅使用向量检索（提交信息较短，BM25 效果有限）
        
        Args:
            query: 查询文本（如 PR 描述、代码变更摘要）
            owner: GitHub 仓库所有者 (如 "openai")
            repo: GitHub 仓库名 (如 "GPT-5")
            top_k: 返回数量
            
        Returns:
            提交记录列表，包含 id, document, metadata, distance
        """
        if not query:
            return []
            
        try:
            # 1. 生成查询向量
            query_embedding = (
                await self.embedding_service.get_embeddings([query])
            )[0]
            
            # 2. 构建过滤条件（Chroma 查询语法）
            #    仅返回该仓库的提交记录
            #    $and: 多个条件 AND 组合
            #    type="commit": 过滤为提交类型
            where_clause = {
                "$and": [
                    {"owner": owner},
                    {"repo": repo},
                    {"type": "commit"}
                ]
            }
            
            # 3. 查询向量数据库
            results = self.vector_store.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_clause  # 过滤条件
            )
            
            # 4. 整理返回结果
            if not results["documents"] or not results["documents"][0]:
                return []
                
            retrieved_commits = []
            for i in range(len(results["documents"][0])):
                retrieved_commits.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i]
                })
                
            return retrieved_commits
            
        except Exception as e:
            # 异常处理：返回空列表，不影响主流程
            logger.error(f"Failed to get relevant commits: {e}")
            return []
