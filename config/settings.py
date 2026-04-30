"""配置管理模块"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, Literal
from enum import Enum
from pathlib import Path
import os


class LLMProvider(Enum):
    """LLM 提供商枚举"""
    OLLAMA = "ollama"
    OPENAI = "openai"


class Settings(BaseSettings):
    """应用配置"""

    class Config:
        env_file = ".env"
        extra = "ignore"

    # MySQL 数据库配置
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = ""

    # Milvus 向量数据库配置
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_table_collection: str = "table_semantics"
    milvus_field_collection: str = "field_semantics"
    milvus_vector_dim: int = 1024  # 向量维度，需与嵌入模型匹配

    # LLM 配置 - 选择提供商
    llm_provider: LLMProvider = LLMProvider.OLLAMA  # ollama 或 openai

    # Ollama 配置
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"  # 可替换为 llama3、qwen 等
    ollama_timeout: int = 120  # 超时时间（秒）

    # OpenAI 格式接口配置
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-3.5-turbo"
    openai_timeout: int = 120  # 超时时间（秒）

    # 语义解析配置
    sample_data_size: int = 5  # 获取示例数据条数
    relationship_match_threshold: float = 0.95  # 外键匹配率阈值

    # FastAPI 服务配置
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # 语义存储配置
    semantic_storage_type: str = "chroma"  # "chroma" 或 "milvus"
    semantic_storage_path: str = "./data/chroma"  # ChromaDB 存储路径

    def model_post_init(self, __context):
        """初始化后处理：将相对路径解析为绝对路径，避免 Windows 下 ChromaDB 报错"""
        self.semantic_storage_path = str(Path(self.semantic_storage_path).resolve())

    # 日志级别配置 (可通过 LOG_LEVEL 环境变量设置)
    log_level: str = Field(
        default="INFO",
        description="日志级别：DEBUG/INFO/WARNING/ERROR",
        validation_alias="LOG_LEVEL"
    )

    # 运行模式配置 (可通过 RUNTIME_MODE 环境变量设置)
    runtime_mode: Literal["auto", "review"] = Field(
        default="auto",
        description="运行模式：auto=自动保存，review=需人工审核",
        validation_alias="RUNTIME_MODE"
    )

    @property
    def effective_runtime_mode(self) -> Literal["auto", "review"]:
        """获取有效的运行模式

        可用于未来扩展（如 CLI 参数覆盖环境变量等）
        """
        return self.runtime_mode


settings = Settings()
