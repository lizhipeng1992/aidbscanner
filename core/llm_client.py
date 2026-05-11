"""LLM client abstraction layer supporting multiple model providers"""
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """LLM provider enumeration"""
    OLLAMA = "ollama"
    OPENAI = "openai"


class ChatMessage:
    """Chat message"""

    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


class ChatResponse:
    """Chat response"""

    def __init__(self, content: str):
        self.content = content


class BaseLLMClient(ABC):
    """Base LLM client class"""

    @abstractmethod
    def chat(
        self,
        messages: List[ChatMessage],
        timeout: Optional[int] = None,
    ) -> ChatResponse:
        """Send chat request

        Args:
            messages: Message list
            timeout: Timeout in seconds

        Returns:
            Chat response

        Raises:
            LLMError: Raised on call failure
        """
        pass


class OllamaClient(BaseLLMClient):
    """Ollama LLM client"""

    def __init__(self, host: str, model: str):
        self.host = host
        self.model = model
        self._client = None

    def _get_client(self):
        """Get Ollama client instance"""
        if self._client is None:
            import ollama
            self._client = ollama.Client(host=self.host)
        return self._client

    def chat(
        self,
        messages: List[ChatMessage],
        timeout: Optional[int] = None,
    ) -> ChatResponse:
        """Call Ollama chat interface"""
        from ollama import RequestError

        client = self._get_client()

        try:
            response = client.chat(
                model=self.model,
                messages=[msg.to_dict() for msg in messages],
                timeout=timeout,
            )

            return ChatResponse(content=response["message"]["content"])

        except RequestError as e:
            raise LLMError(f"Ollama call failed: {e}")
        except Exception as e:
            raise LLMError(f"Ollama call error: {e}")


class OpenAIClient(BaseLLMClient):
    """OpenAI-format LLM client"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        """Get OpenAI client instance"""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
            )
        return self._client

    def chat(
        self,
        messages: List[ChatMessage],
        timeout: Optional[int] = None,
    ) -> ChatResponse:
        """Call OpenAI-format chat interface"""
        from openai import APIError

        client = self._get_client()

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[msg.to_dict() for msg in messages],
                timeout=timeout,
            )

            return ChatResponse(content=response.choices[0].message.content)

        except APIError as e:
            raise LLMError(f"OpenAI API call failed: {e}")
        except Exception as e:
            raise LLMError(f"OpenAI API call error: {e}")


class LLMError(Exception):
    """LLM call error"""
    pass


def create_llm_client(provider: LLMProvider, config: Dict[str, Any]) -> BaseLLMClient:
    """Factory function to create LLM client

    Args:
        provider: LLM provider type
        config: Configuration parameters

    Returns:
        LLM client instance

    Raises:
        ValueError: Unknown provider type
    """
    if provider == LLMProvider.OLLAMA:
        return OllamaClient(
            host=config.get("host", "http://localhost:11434"),
            model=config.get("model", "qwen2.5:7b"),
        )
    elif provider == LLMProvider.OPENAI:
        return OpenAIClient(
            base_url=config.get("base_url", "https://api.openai.com/v1"),
            api_key=config.get("api_key", ""),
            model=config.get("model", "gpt-3.5-turbo"),
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
