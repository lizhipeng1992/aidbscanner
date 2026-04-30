"""知识基类，用于管理语义数据的存储和检索"""
import logging
from typing import List, Optional, Dict, Any

from .models import FieldSemantic, TableSemantic, Relationship
from .vector_store import MilvusVectorStore
from .embedding import BaseEmbeddingService, OllamaEmbeddingService, OpenAIEmbeddingService
from config.settings import settings

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """知识基，管理语义数据的向量化存储和检索"""

    def __init__(
        self,
        vector_store: Optional[MilvusVectorStore] = None,
        embedding_service: Optional[BaseEmbeddingService] = None,
    ):
        """初始化知识基

        Args:
            vector_store: 向量存储实例
            embedding_service: 嵌入服务实例
        """
        self.vector_store = vector_store or MilvusVectorStore(
            host=settings.milvus_host,
            port=settings.milvus_port,
            collection=None,
            vector_dim=settings.milvus_vector_dim,
        )

        # 根据配置创建嵌入服务
        if embedding_service is not None:
            self.embedding_service = embedding_service
        else:
            if settings.llm_provider.value == "ollama":
                self.embedding_service = OllamaEmbeddingService(
                    host=settings.ollama_host,
                    model="nomic-embed-text",
                )
            else:
                self.embedding_service = OpenAIEmbeddingService(
                    base_url=settings.openai_base_url,
                    api_key=settings.openai_api_key,
                    model="text-embedding-3-small",
                    dimensions=1536,
                )

    def connect(self) -> None:
        """连接到向量数据库"""
        self.vector_store.connect()
        # 迁移：删除旧集合
        if self.vector_store.has_collection("db_semantics"):
            self.vector_store.drop_collection("db_semantics")
            logger.info("已迁移：删除旧集合 db_semantics")
        # 创建两个新集合
        self.vector_store.create_collection(
            collection_name=settings.milvus_table_collection,
            dimension=settings.milvus_vector_dim,
        )
        self.vector_store.create_collection(
            collection_name=settings.milvus_field_collection,
            dimension=settings.milvus_vector_dim,
        )

    def disconnect(self) -> None:
        """断开连接"""
        self.vector_store.disconnect()

    def store_field_semantic(self, field: FieldSemantic) -> None:
        """存储字段语义信息

        Args:
            field: 字段语义对象
        """
        try:
            # 构造要嵌入的文本
            text = self._build_field_text(field)

            # 生成向量
            vector = self.embedding_service.embed_text(text)

            # 准备数据
            data = [
                {
                    "id": field.id,
                    "db_name": field.db_name,
                    "table_name": field.table_name,
                    "column_name": field.column_name,
                    "data_type": field.data_type,
                    "chinese_name": field.chinese_name or "",
                    "business_definition": field.business_definition or "",
                    "value_rules": field.value_rules or "",
                    "data_category": field.data_category.value,
                    "created_at": field.created_at.isoformat() if hasattr(field, "created_at") else "",
                }
            ]

            # 插入向量数据库
            self.vector_store.insert(
                collection_name=settings.milvus_field_collection,
                vectors=[vector],
                data=data,
            )
            logger.info(f"存储字段语义：{field.id}")

        except Exception as e:
            logger.error(f"存储字段语义失败：{e}")

    def store_table_semantic(self, table: TableSemantic) -> None:
        """存储表语义信息

        Args:
            table: 表语义对象
        """
        # 存储表级语义到 table_semantics
        try:
            text = f"表：{table.table_name} 中文名称：{table.chinese_name or ''} 定义：{table.business_definition or ''}"
            vector = self.embedding_service.embed_text(text)

            data = [
                {
                    "id": f"{table.db_name}.{table.table_name}",
                    "db_name": table.db_name,
                    "table_name": table.table_name,
                    "column_name": "",
                    "data_type": "",
                    "chinese_name": table.chinese_name or "",
                    "business_definition": table.business_definition or "",
                    "value_rules": "",
                    "data_category": table.data_category.value,
                    "created_at": "",
                }
            ]

            self.vector_store.insert(
                collection_name=settings.milvus_table_collection,
                vectors=[vector],
                data=data,
            )
            logger.info(f"存储表语义：{table.table_name}")

        except Exception as e:
            logger.error(f"存储表语义失败：{e}")

        # 存储字段级别语义
        for field in table.field_semantics:
            self.store_field_semantic(field)

    def search_similar_fields(
        self,
        query: str,
        db_name: Optional[str] = None,
        table_name: Optional[str] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """搜索相似的字段

        Args:
            query: 查询文本
            db_name: 数据库名过滤（可选）
            table_name: 表名过滤（可选）
            top_k: 返回结果数量

        Returns:
            搜索结果列表
        """
        try:
            # 生成查询向量
            query_vector = self.embedding_service.embed_text(query)

            # 构建过滤表达式
            filter_expr = None
            if db_name:
                filter_expr = f'db_name == "{db_name}"'
            if table_name:
                if filter_expr:
                    filter_expr += f' and table_name == "{table_name}"'
                else:
                    filter_expr = f'table_name == "{table_name}"'

            # 搜索表集合（优先）
            table_results = self.vector_store.search(
                collection_name=settings.milvus_table_collection,
                query_vector=query_vector,
                top_k=top_k,
                filter_expr=filter_expr,
            )

            # 搜索字段集合
            field_results = self.vector_store.search(
                collection_name=settings.milvus_field_collection,
                query_vector=query_vector,
                top_k=top_k,
                filter_expr=filter_expr,
            )

            # 合并：表结果在前，按 id 去重
            all_results = table_results + field_results
            seen_ids = set()
            merged = []
            for r in all_results:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    merged.append(r)

            results = merged[:top_k]

            return results

        except Exception as e:
            logger.error(f"搜索相似字段失败：{e}")
            return []

    def get_fields_by_table(
        self, db_name: str, table_name: str
    ) -> List[Dict[str, Any]]:
        """获取指定表的所有字段语义

        Args:
            db_name: 数据库名
            table_name: 表名

        Returns:
            字段语义列表
        """
        try:
            filter_expr = f'db_name == "{db_name}" and table_name == "{table_name}"'
            results = self.vector_store.search(
                collection_name=settings.milvus_field_collection,
                query_vector=[0] * self.embedding_service.dimension,
                top_k=100,
                filter_expr=filter_expr,
            )
            return results
        except Exception as e:
            logger.error(f"获取表字段失败：{e}")
            return []

    def _build_field_text(self, field: FieldSemantic) -> str:
        """构建字段嵌入文本

        Args:
            field: 字段语义对象

        Returns:
            用于嵌入的文本
        """
        parts = [
            f"字段：{field.column_name}",
            f"表：{field.table_name}",
            f"类型：{field.data_type}",
        ]

        if field.chinese_name:
            parts.append(f"中文名称：{field.chinese_name}")
        if field.business_definition:
            parts.append(f"业务定义：{field.business_definition}")
        if field.value_rules:
            parts.append(f"取值规则：{field.value_rules}")
        if field.data_category:
            parts.append(f"数据分类：{field.data_category.value}")

        return " ".join(parts)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
