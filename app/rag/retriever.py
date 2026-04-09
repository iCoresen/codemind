import logging
from typing import List, Dict, Any
from rank_bm25 import BM25Okapi

from app.rag.vector_store import ChromaVectorStore
from app.rag.embedding_service import EmbeddingService

logger = logging.getLogger("codemind.rag.retriever")

class RAGRetriever:
    def __init__(
        self,
        vector_store: ChromaVectorStore,
        embedding_service: EmbeddingService
    ):
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self._bm25_corpus = {} # key: doc_id, value: tokens
        
    def build_bm25_index(self, docs: List[Dict[str, Any]]):
        """Build BM25 index over documents for keyword retrieval"""
        corpus = [doc['text'].lower().split() for doc in docs]
        self.bm25 = BM25Okapi(corpus)
        self._bm25_docs = docs

    async def hybrid_search_docs(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Hybrid search for documents (Vector + BM25 keyword matching)
        """
        if not query:
            return []
            
        try:
            # 1. Vector Search
            query_embedding = (await self.embedding_service.get_embeddings([query]))[0]
            vector_results = self.vector_store.query_docs(
                query_embeddings=[query_embedding],
                n_results=top_k * 2
            )
            
            vector_scored_docs = {}
            if vector_results["documents"] and vector_results["documents"][0]:
                for i in range(len(vector_results["documents"][0])):
                    doc_id = vector_results["ids"][0][i]
                    # Convert distance to a similarity score (inverse)
                    vector_score = 1.0 / (1.0 + vector_results["distances"][0][i])
                    vector_scored_docs[doc_id] = {
                        "id": doc_id,
                        "document": vector_results["documents"][0][i],
                        "metadata": vector_results["metadatas"][0][i],
                        "vector_score": vector_score
                    }
                    
            # 2. BM25 Search
            bm25_scored_docs = {}
            if hasattr(self, 'bm25'):
                tokenized_query = query.lower().split()
                doc_scores = self.bm25.get_scores(tokenized_query)
                # Get top 2*k BM25 hits
                top_n = sorted(range(len(doc_scores)), key=lambda i: doc_scores[i], reverse=True)[:top_k*2]
                for idx in top_n:
                    if doc_scores[idx] > 0:
                        doc = self._bm25_docs[idx]
                        doc_id = doc["id"]
                        bm25_scored_docs[doc_id] = {
                            "id": doc_id,
                            "document": doc["text"],
                            "metadata": doc["metadata"],
                            "bm25_score": doc_scores[idx]
                        }
            
            # 3. Reciprocal Rank Fusion (RRF) for Hybrid Scored Docs
            fused_scores = {}
            k = 60 # RRF constant
            
            # Rank Vector docs
            vector_ranked = sorted(vector_scored_docs.values(), key=lambda x: x["vector_score"], reverse=True)
            for rank, doc in enumerate(vector_ranked):
                doc_id = doc["id"]
                if doc_id not in fused_scores:
                    fused_scores[doc_id] = {"doc": doc, "score": 0.0}
                fused_scores[doc_id]["score"] += 1.0 / (k + rank + 1)
                
            # Rank BM25 docs
            bm25_ranked = sorted(bm25_scored_docs.values(), key=lambda x: x["bm25_score"], reverse=True)
            for rank, doc in enumerate(bm25_ranked):
                doc_id = doc["id"]
                if doc_id not in fused_scores:
                    fused_scores[doc_id] = {"doc": doc, "score": 0.0}
                fused_scores[doc_id]["score"] += 1.0 / (k + rank + 1)
            
            # Get top K fused results
            sorted_fused = sorted(fused_scores.values(), key=lambda x: x["score"], reverse=True)
            return [item["doc"] for item in sorted_fused[:top_k]]
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []

    async def get_relevant_commits(self, query: str, owner: str, repo: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Get the most relevant commits for a given query in a specific repository.
        """
        if not query:
            return []
            
        try:
            query_embedding = (await self.embedding_service.get_embeddings([query]))[0]
            
            where_clause = {
                "$and": [
                    {"owner": owner},
                    {"repo": repo},
                    {"type": "commit"}
                ]
            }
            
            results = self.vector_store.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_clause
            )
            
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
            # Handle graceful fallback
            return []