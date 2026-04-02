from abc import ABC, abstractmethod
from typing import Tuple


class BaseAIHandler(ABC):
    @abstractmethod
    async def async_chat_completion(self, system: str, user: str, temperature: float = 0.2) -> Tuple[str, str]:
        pass
