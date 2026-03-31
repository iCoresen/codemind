import logging
import os
from typing import Tuple

from litellm import completion, acompletion

from app.config import Settings

logger = logging.getLogger("codemind.ai")

class AIHandler:
    def __init__(self, settings: Settings):
        self.settings = settings
        os.environ["DEEPSEEK_API_KEY"] = settings.deepseek_api_key

    def chat_completion(
        self, system: str, user: str, temperature: float = 0.2
    ) -> Tuple[str, str]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        
        try:
            response = completion(
                model=self.settings.deepseek_model,
                messages=messages,
                temperature=temperature,
                timeout=self.settings.ai_timeout,
            )
            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            return content, finish_reason
        except Exception as e:
            logger.error(f"Failed to generate completion: {e}")
            raise

    async def async_chat_completion(
        self, system: str, user: str, temperature: float = 0.2
    ) -> Tuple[str, str]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        
        try:
            response = await acompletion(
                model=self.settings.deepseek_model,
                messages=messages,
                temperature=temperature,
                timeout=self.settings.ai_timeout,
            )
            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            return content, finish_reason
        except Exception as e:
            logger.error(f"Failed to generate async completion: {e}")
            raise
