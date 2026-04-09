import logging
from typing import List

from app.ai_handlers.base_ai_handler import BaseAIHandler

logger = logging.getLogger("codemind.rag.embedding")

class EmbeddingService:
    def __init__(self, ai_handler: BaseAIHandler):
        self.ai_handler = ai_handler

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        
        try:
            return await self.ai_handler.async_embedding(texts)
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise