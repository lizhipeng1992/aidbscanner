"""LLM 客户端抽象层，支持多种大模型接入方式"""
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """LLM 提供商枚举"""
    OLLAMA = "ollama"
    OPENAI = "openai"


class ChatMessage:
    """聊天消息"""

    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


class ChatResponse:
    """聊天响应"""

    def __init__(self, content: str):
        self.content = content


class BaseLLMClient(ABC):
    """LLM 客户端基类"""

    @abstractmethod
    def chat(
        self,
        messages: List[ChatMessage],
        timeout: Optional[int] = None,
    ) -> ChatResponse:
        """发送聊天请求

        Args:
            messages: 消息列表
            timeout: 超时时间（秒）

        Returns:
            聊天响应

        Raises:
            LLMError: 调用失败时抛出
        """
        pass


class OllamaClient(BaseLLMClient):
    """Ollama LLM 客户端"""

    def __init__(self, host: str, model: str):
        self.host = host
        self.model = model
        self._client = None

    def _get_client(self):
        """获取 Ollama 客户端实例"""
        if self._client is None:
            import ollama
            self._client = ollama.Client(host=self.host)
        return self._client

    def chat(
        self,
        messages: List[ChatMessage],
        timeout: Optional[int] = None,
    ) -> ChatResponse:
        """调用 Ollama 聊天接口"""
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
            raise LLMError(f"Ollama 调用失败：{e}")
        except Exception as e:
            raise LLMError(f"Ollama 调用异常：{e}")


class OpenAIClient(BaseLLMClient):
    """OpenAI 格式 LLM 客户端"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        """获取 OpenAI 客户端实例"""
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
        """调用 OpenAI 格式聊天接口"""
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
            raise LLMError(f"OpenAI API 调用失败：{e}")
        except Exception as e:
            raise LLMError(f"OpenAI API 调用异常：{e}")


class LLMError(Exception):
    """LLM 调用异常"""
    pass


def create_llm_client(provider: LLMProvider, config: Dict[str, Any]) -> BaseLLMClient:
    """创建 LLM 客户端工厂函数

    Args:
        provider: LLM 提供商类型
        config: 配置参数

    Returns:
        LLM 客户端实例

    Raises:
        ValueError: 未知的提供商类型
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
        raise ValueError(f"未知的 LLM 提供商：{provider}")
