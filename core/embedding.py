"""Text embedding service for converting text to vectors"""
import logging
from typing import List, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseEmbeddingService(ABC):
    """Base class for embedding services"""

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Convert a single text to a vector

        Args:
            text: Input text

        Returns:
            Vector representation
        """
        pass

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Batch convert texts to vectors

        Args:
            texts: Input text list

        Returns:
            Vector list
        """
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return vector dimension"""
        pass


class OllamaEmbeddingService(BaseEmbeddingService):
    """Ollama-based embedding service"""

    def __init__(self, host: str, model: str = "nomic-embed-text"):
        """Initialize Ollama embedding service.

        Args:
            host: Ollama host address
            model: Embedding model name
        """
        self.host = host
        self.model = model
        self._dimension = 768  # nomic-embed-text default dimension

    def embed_text(self, text: str) -> List[float]:
        """Convert a single text to a vector"""
        try:
            import ollama

            client = ollama.Client(host=self.host)
            response = client.embeddings(model=self.model, prompt=text)
            return response["embedding"]
        except Exception as e:
            logger.error(f"Ollama embedding failed: {e}")
            raise

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Batch convert texts to vectors"""
        return [self.embed_text(text) for text in texts]

    @property
    def dimension(self) -> int:
        return self._dimension


class OpenAIEmbeddingService(BaseEmbeddingService):
    """OpenAI-compatible embedding service"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: Optional[int] = None,
    ):
        """Initialize OpenAI embedding service.

        Args:
            base_url: API base URL
            api_key: API key
            model: Embedding model name
            dimensions: Vector dimensions (optional)
        """
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self._dimensions = dimensions or 1536  # default dimension
        self._client = None

    def _get_client(self):
        """Get OpenAI client"""
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def embed_text(self, text: str) -> List[float]:
        """Convert a single text to a vector"""
        try:
            client = self._get_client()
            kwargs = {"model": self.model, "input": text}
            if self._dimensions:
                kwargs["dimensions"] = self._dimensions

            response = client.embeddings.create(**kwargs)
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}")
            raise

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Batch convert texts to vectors"""
        try:
            client = self._get_client()
            kwargs = {"model": self.model, "input": texts}
            if self._dimensions:
                kwargs["dimensions"] = self._dimensions

            response = client.embeddings.create(**kwargs)
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"OpenAI batch embedding failed: {e}")
            # Fallback to embedding one by one
            return [self.embed_text(text) for text in texts]

    @property
    def dimension(self) -> int:
        return self._dimensions
