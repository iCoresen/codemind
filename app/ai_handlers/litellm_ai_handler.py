import logging
import os
from typing import Tuple

from litellm import completion, acompletion

from app.config import Settings
from app.ai_handlers.base_ai_handler import BaseAIHandler

logger = logging.getLogger("codemind.ai")

class LiteLLMAIHandler(BaseAIHandler):
    def __init__(self, settings: Settings):
        self.settings = settings
        if self.settings.ai_api_key:
            os.environ["LITELLM_API_KEY"] = self.settings.ai_api_key

    def _get_litellm_kwargs(self):
        kwargs = {}
        if self.settings.ai_base_url:
            kwargs["api_base"] = self.settings.ai_base_url
        if self.settings.ai_api_key:
            kwargs["api_key"] = self.settings.ai_api_key
        if self.settings.ai_fallback_models:
            kwargs["fallbacks"] = [m.strip() for m in self.settings.ai_fallback_models.split(",") if m.strip()]
        return kwargs

    def chat_completion(
        self, system: str, user: str, temperature: float = 0.2
    ) -> Tuple[str, str]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        
        try:
            kwargs = self._get_litellm_kwargs()
            response = completion(
                model=self.settings.ai_model,
                messages=messages,
                temperature=temperature,
                timeout=self.settings.ai_timeout,
                **kwargs
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
            kwargs = self._get_litellm_kwargs()
            response = await acompletion(
                model=self.settings.ai_model,
                messages=messages,
                temperature=temperature,
                timeout=self.settings.ai_timeout,
                **kwargs
            )
            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            return content, finish_reason
        except Exception as e:
            logger.error(f"Failed to generate async completion: {e}")
            raise