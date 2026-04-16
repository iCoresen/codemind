import logging
from typing import List, Optional

from app.ai_handlers.base_ai_handler import BaseAIHandler
from app.config import Settings

logger = logging.getLogger("codemind.rag.embedding")

class EmbeddingService:
    def __init__(self, ai_handler: BaseAIHandler, settings: Settings):
        self.ai_handler = ai_handler
        self.settings = settings

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        
        try:
            return await self.ai_handler.async_embedding(
                texts,
                model=self.settings.ai_embedding_model,
                api_key=self.settings.ai_embedding_api_key or None,
                base_url=self.settings.ai_embedding_base_url or None,
            )
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise
