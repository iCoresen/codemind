import logging
import os
from typing import Tuple, Optional

from litellm import completion, acompletion

from app.config import Settings
from app.ai_handlers.base_ai_handler import BaseAIHandler
from app.exceptions import AIProviderError

logger = logging.getLogger("codemind.ai")

class LiteLLMAIHandler(BaseAIHandler):
    def __init__(self, settings: Settings):
        self.settings = settings
        if self.settings.ai_api_key:
            os.environ["LITELLM_API_KEY"] = self.settings.ai_api_key
            
        self._cached_fallback_str = None
        self._parsed_fallbacks = None

    def _get_parsed_fallbacks(self):
        current_str = self.settings.ai_fallback_models
        if not current_str:
            return None
        
        # 当配置的字符串发生变化时才重新解析
        if current_str != self._cached_fallback_str:
            self._parsed_fallbacks = self._parse_fallback_models(current_str)
            self._cached_fallback_str = current_str
            
        return self._parsed_fallbacks

    def _parse_fallback_models(self, fallback_models_str: str) -> list:
        fallbacks = []
        import json
        
        # 智能解析逗号分隔的字符串，处理 JSON 对象内部的逗号
        parts = []
        current_part = []
        brace_count = 0
        
        for char in fallback_models_str:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
            
            if char == ',' and brace_count == 0:
                # 不在 JSON 对象内部的逗号，分割点
                parts.append(''.join(current_part).strip())
                current_part = []
            else:
                current_part.append(char)
        
        # 添加最后一部分
        if current_part:
            parts.append(''.join(current_part).strip())
        
        # 处理每个部分
        for part in parts:
            if not part:
                continue
            
            # 检查是否是 JSON 格式的字典配置
            if part.startswith("{") and part.endswith("}"):
                try:
                    model_config = json.loads(part)
                    fallbacks.append(model_config)
                except json.JSONDecodeError:
                    # 如果 JSON 解析失败，当作普通字符串处理
                    fallbacks.append(part)
            else:
                fallbacks.append(part)
        
        return fallbacks

    def _get_litellm_kwargs(self):
        kwargs = {}
        if self.settings.ai_base_url:
            kwargs["api_base"] = self.settings.ai_base_url
        if self.settings.ai_api_key:
            kwargs["api_key"] = self.settings.ai_api_key
            
        parsed_fallbacks = self._get_parsed_fallbacks()
        if parsed_fallbacks:
            kwargs["fallbacks"] = parsed_fallbacks
        return kwargs

    def _get_embedding_kwargs(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> dict:
        """构建 embedding 调用参数，优先使用传入的独立配置"""
        kwargs = {}
        
        # 优先使用独立的 embedding 配置
        if base_url:
            kwargs["api_base"] = base_url
        elif self.settings.ai_embedding_base_url:
            kwargs["api_base"] = self.settings.ai_embedding_base_url
            
        if api_key:
            kwargs["api_key"] = api_key
        elif self.settings.ai_embedding_api_key:
            kwargs["api_key"] = self.settings.ai_embedding_api_key
            
        return kwargs

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
            raise AIProviderError(f"LiteLLM async completion error: {e}") from e

    async def async_embedding(
        self,
        texts: list[str],
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> list[list[float]]:
        from litellm import aembedding
        try:
            kwargs = self._get_embedding_kwargs(api_key=api_key, base_url=base_url)
            embedding_model = model or self.settings.ai_embedding_model
            response = await aembedding(
                model=embedding_model,
                input=texts,
                timeout=self.settings.ai_timeout,
                **kwargs
            )
            return [data['embedding'] for data in response.data]
        except Exception as e:
            logger.error(f"Failed to generate async embedding: {e}")
            raise AIProviderError(f"LiteLLM async embedding error: {e}") from e

