import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("codemind.rag.evaluation")

class RAGEvaluator:
    """
    RAG Quality Evaluation System
    Used to track the effectiveness of retrieved contexts.
    """
    def __init__(self):
        self.logs: List[Dict[str, Any]] = []

    def evaluate_retrieval(
        self,
        query: str,
        retrieved_docs: List[str],
        ground_truth_docs: Optional[List[str]] = None,
        context_relevance: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Record and evaluate a single retrieval event.
        - hit_rate: if ground truth is provided
        - relevance: LLM/user provided relevance score
        """
        eval_result = {
            "query": query,
            "retrieved_count": len(retrieved_docs),
            "relevance_score": context_relevance,
            "metadata": metadata or {}
        }
        
        if ground_truth_docs:
            hits = [doc for doc in retrieved_docs if doc in ground_truth_docs]
            eval_result["hit_rate"] = len(hits) / len(ground_truth_docs) if ground_truth_docs else 0.0
            
        self.logs.append(eval_result)
        logger.info(f"RAG Evaluation: {eval_result}")
        return eval_result

    def calculate_average_metrics(self) -> Dict[str, float]:
        """
        Calculate global RAG quality metrics
        """
        if not self.logs:
            return {"avg_relevance": 0.0, "avg_hit_rate": 0.0}
            
        total_relevance = sum([log.get("relevance_score", 0.0) for log in self.logs])
        total_hit_rates = sum([log.get("hit_rate", 0.0) for log in self.logs if "hit_rate" in log])
        hit_rate_logs_count = sum([1 for log in self.logs if "hit_rate" in log])
        
        return {
            "avg_relevance": total_relevance / len(self.logs),
            "avg_hit_rate": total_hit_rates / hit_rate_logs_count if hit_rate_logs_count > 0 else 0.0
        }