import logging
import os
from typing import Tuple

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

    def _get_litellm_kwargs(self):
        kwargs = {}
        if self.settings.ai_base_url:
            kwargs["api_base"] = self.settings.ai_base_url
        if self.settings.ai_api_key:
            kwargs["api_key"] = self.settings.ai_api_key
        if self.settings.ai_fallback_models:
            fallbacks = []
            import json
            
            # 智能解析逗号分隔的字符串，处理 JSON 对象内部的逗号
            parts = []
            current_part = []
            brace_count = 0
            
            for char in self.settings.ai_fallback_models:
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
            
            kwargs["fallbacks"] = fallbacks
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
            raise AIProviderError(f"LiteLLM completion error: {e}") from e

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