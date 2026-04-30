"""文本嵌入服务，用于将文本转换为向量"""
import logging
from typing import List, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseEmbeddingService(ABC):
    """嵌入服务基类"""

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """将单个文本转换为向量

        Args:
            text: 输入文本

        Returns:
            向量表示
        """
        pass

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量将文本转换为向量

        Args:
            texts: 输入文本列表

        Returns:
            向量列表
        """
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """返回向量维度"""
        pass


class OllamaEmbeddingService(BaseEmbeddingService):
    """使用 Ollama 的嵌入服务"""

    def __init__(self, host: str, model: str = "nomic-embed-text"):
        """初始化 Ollama 嵌入服务

        Args:
            host: Ollama 主机地址
            model: 嵌入模型名称
        """
        self.host = host
        self.model = model
        self._dimension = 768  # nomic-embed-text 默认维度

    def embed_text(self, text: str) -> List[float]:
        """将单个文本转换为向量"""
        try:
            import ollama

            client = ollama.Client(host=self.host)
            response = client.embeddings(model=self.model, prompt=text)
            return response["embedding"]
        except Exception as e:
            logger.error(f"Ollama 嵌入失败：{e}")
            raise

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量将文本转换为向量"""
        return [self.embed_text(text) for text in texts]

    @property
    def dimension(self) -> int:
        return self._dimension


class OpenAIEmbeddingService(BaseEmbeddingService):
    """使用 OpenAI 格式的嵌入服务"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: Optional[int] = None,
    ):
        """初始化 OpenAI 嵌入服务

        Args:
            base_url: API 基础 URL
            api_key: API 密钥
            model: 嵌入模型名称
            dimensions: 向量维度（可选）
        """
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self._dimensions = dimensions or 1536  # 默认维度
        self._client = None

    def _get_client(self):
        """获取 OpenAI 客户端"""
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def embed_text(self, text: str) -> List[float]:
        """将单个文本转换为向量"""
        try:
            client = self._get_client()
            kwargs = {"model": self.model, "input": text}
            if self._dimensions:
                kwargs["dimensions"] = self._dimensions

            response = client.embeddings.create(**kwargs)
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI 嵌入失败：{e}")
            raise

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量将文本转换为向量"""
        try:
            client = self._get_client()
            kwargs = {"model": self.model, "input": texts}
            if self._dimensions:
                kwargs["dimensions"] = self._dimensions

            response = client.embeddings.create(**kwargs)
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"OpenAI 批量嵌入失败：{e}")
            # 回退到逐个嵌入
            return [self.embed_text(text) for text in texts]

    @property
    def dimension(self) -> int:
        return self._dimensions
