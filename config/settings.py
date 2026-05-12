"""Configuration management module"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, Literal
from enum import Enum
from pathlib import Path
import os


class LLMProvider(Enum):
    """LLM provider enumeration"""
    OLLAMA = "ollama"
    OPENAI = "openai"


class Settings(BaseSettings):
    """Application configuration"""

    class Config:
        env_file = ".env"
        extra = "ignore"

    # Database connection configuration
    db_type: Literal["mysql", "gbase", "sqlserver"] = "mysql"
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_database: str = ""

    # Milvus vector database configuration
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_table_collection: str = "table_semantics"
    milvus_field_collection: str = "field_semantics"
    milvus_vector_dim: int = 1024  # Vector dimension, must match embedding model

    # LLM configuration - provider selection
    llm_provider: LLMProvider = LLMProvider.OLLAMA  # ollama or openai

    # Ollama configuration
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"  # can be replaced with llama3, qwen, etc.
    ollama_timeout: int = 120  # Timeout (seconds)

    # OpenAI-compatible API configuration
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-3.5-turbo"
    openai_timeout: int = 120  # Timeout (seconds)

    # Semantic analysis configuration
    sample_data_size: int = 5  # Number of sample data rows to fetch
    relationship_match_threshold: float = 0.95  # Foreign key match rate threshold

    # FastAPI service configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Semantic storage configuration
    semantic_storage_type: str = "chroma"  # "chroma" or "milvus"
    semantic_storage_path: str = "./data/chroma"  # ChromaDB storage path

    def model_post_init(self, __context):
        """Post-initialization: resolve relative paths to absolute paths to avoid Windows ChromaDB errors"""
        self.semantic_storage_path = str(Path(self.semantic_storage_path).resolve())

    # Log level configuration (can be set via LOG_LEVEL env var)
    log_level: str = Field(
        default="INFO",
        description="Log level: DEBUG/INFO/WARNING/ERROR",
        validation_alias="LOG_LEVEL"
    )

    # Runtime mode configuration (can be set via RUNTIME_MODE env var)
    runtime_mode: Literal["auto", "review"] = Field(
        default="auto",
        description="Runtime mode: auto=auto-save, review=requires manual review",
        validation_alias="RUNTIME_MODE"
    )

    @property
    def effective_runtime_mode(self) -> Literal["auto", "review"]:
        """Get effective runtime mode

        Reserved for future extension (e.g. CLI args overriding env vars)
        """
        return self.runtime_mode


settings = Settings()
