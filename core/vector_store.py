"""Milvus 向量数据库存储接口"""
import logging
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod

from .models import FieldSemantic, TableSemantic, Relationship

logger = logging.getLogger(__name__)


class BaseVectorStore(ABC):
    """向量存储基类"""

    @abstractmethod
    def connect(self) -> None:
        """连接到向量数据库"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
        pass

    @abstractmethod
    def create_collection(self, collection_name: str, dimension: int) -> None:
        """创建集合（表）"""
        pass

    @abstractmethod
    def drop_collection(self, collection_name: str) -> None:
        """删除集合"""
        pass

    @abstractmethod
    def has_collection(self, collection_name: str) -> bool:
        """检查集合是否存在"""
        pass

    @abstractmethod
    def insert(self, collection_name: str, vectors: List[List[float]], data: List[Dict[str, Any]]) -> None:
        """插入向量数据"""
        pass

    @abstractmethod
    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 10,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """搜索相似向量"""
        pass

    @abstractmethod
    def get(self, collection_name: str, ids: List[str]) -> List[Dict[str, Any]]:
        """根据 ID 获取数据"""
        pass

    @abstractmethod
    def delete(self, collection_name: str, filter_expr: str) -> None:
        """删除数据"""
        pass


class MilvusVectorStore(BaseVectorStore):
    """Milvus 向量数据库实现"""

    def __init__(self, host: str, port: int, collection: Optional[str] = None, vector_dim: int = 1024):
        """初始化 Milvus 向量存储

        Args:
            host: Milvus 主机地址
            port: Milvus 端口
            collection: 集合名称
            vector_dim: 向量维度
        """
        self.host = host
        self.port = port
        self.collection_name = collection
        self.vector_dim = vector_dim
        self._client = None
        self._connected = False

    def connect(self) -> None:
        """连接到 Milvus"""
        if self._connected:
            return

        try:
            from pymilvus import connections, utility

            # 连接 Milvus
            connections.connect(
                alias="default",
                host=self.host,
                port=self.port,
            )

            # 检查连接状态
            if utility.has_connection("default"):
                self._connected = True
                logger.info(f"成功连接到 Milvus: {self.host}:{self.port}")
            else:
                raise ConnectionError("无法连接到 Milvus")

        except Exception as e:
            logger.error(f"连接 Milvus 失败：{e}")
            raise

    def disconnect(self) -> None:
        """断开连接"""
        if not self._connected:
            return

        try:
            from pymilvus import connections

            connections.disconnect("default")
            self._connected = False
            logger.info("已断开 Milvus 连接")
        except Exception as e:
            logger.error(f"断开 Milvus 连接失败：{e}")

    def create_collection(self, collection_name: Optional[str] = None, dimension: Optional[int] = None) -> None:
        """创建集合

        Args:
            collection_name: 集合名称，默认使用初始化时的名称
            dimension: 向量维度，默认使用初始化时的维度
        """
        from pymilvus import FieldSchema, CollectionSchema, DataType, Collection

        collection_name = collection_name or self.collection_name
        dimension = dimension or self.vector_dim

        # 检查集合是否已存在
        if self.has_collection(collection_name):
            logger.info(f"集合 {collection_name} 已存在，跳过创建")
            return

        # 定义字段
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=256, is_primary=True),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dimension),
            FieldSchema(name="db_name", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="table_name", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="column_name", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="data_type", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="chinese_name", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="business_definition", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="value_rules", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="data_category", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="created_at", dtype=DataType.VARCHAR, max_length=64),
        ]

        schema = CollectionSchema(fields, "语义元数据集合")

        # 创建集合
        collection = Collection(collection_name, schema)
        logger.info(f"创建集合：{collection_name}")

        # 为向量字段创建索引
        index_params = {
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {"M": 8, "efConstruction": 200},
        }
        collection.create_index("vector", index_params)
        logger.info(f"为集合 {collection_name} 创建向量索引")

    def drop_collection(self, collection_name: Optional[str] = None) -> None:
        """删除集合"""
        from pymilvus import utility

        collection_name = collection_name or self.collection_name

        if self.has_collection(collection_name):
            utility.drop_collection(collection_name)
            logger.info(f"删除集合：{collection_name}")

    def has_collection(self, collection_name: Optional[str] = None) -> bool:
        """检查集合是否存在"""
        from pymilvus import utility

        collection_name = collection_name or self.collection_name
        return utility.has_collection(collection_name)

    def insert(
        self,
        collection_name: Optional[str] = None,
        vectors: Optional[List[List[float]]] = None,
        data: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """插入向量数据

        Args:
            collection_name: 集合名称
            vectors: 向量列表
            data: 数据列表，每个元素是包含字段值的字典
        """
        from pymilvus import Collection

        collection_name = collection_name or self.collection_name
        collection = Collection(collection_name)

        # 准备插入数据
        entities = []
        for field in collection.schema.fields:
            if field.name == "vector":
                entities.extend(vectors)
            else:
                field_data = [item.get(field.name, "") for item in data]
                entities.extend(field_data)

        collection.insert(entities)
        collection.flush()
        logger.info(f"插入 {len(vectors)} 条数据到集合 {collection_name}")

    def search(
        self,
        collection_name: Optional[str] = None,
        query_vector: Optional[List[float]] = None,
        top_k: int = 10,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """搜索相似向量

        Args:
            collection_name: 集合名称
            query_vector: 查询向量
            top_k: 返回结果数量
            filter_expr: 过滤表达式

        Returns:
            搜索结果列表
        """
        from pymilvus import Collection

        collection_name = collection_name or self.collection_name
        collection = Collection(collection_name)

        search_params = {
            "metric_type": "COSINE",
            "params": {"ef": 64},
        }

        results = collection.search(
            data=[query_vector],
            anns_field="vector",
            param=search_params,
            limit=top_k,
            expr=filter_expr,
            output_fields=[
                "id",
                "db_name",
                "table_name",
                "column_name",
                "data_type",
                "chinese_name",
                "business_definition",
                "value_rules",
                "data_category",
            ],
        )

        # 解析搜索结果
        search_results = []
        for result in results[0]:
            search_results.append(
                {
                    "id": result.entity.get("id"),
                    "distance": result.distance,
                    "db_name": result.entity.get("db_name"),
                    "table_name": result.entity.get("table_name"),
                    "column_name": result.entity.get("column_name"),
                    "data_type": result.entity.get("data_type"),
                    "chinese_name": result.entity.get("chinese_name"),
                    "business_definition": result.entity.get("business_definition"),
                    "value_rules": result.entity.get("value_rules"),
                    "data_category": result.entity.get("data_category"),
                }
            )

        return search_results

    def get(self, collection_name: Optional[str] = None, ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """根据 ID 获取数据

        Args:
            collection_name: 集合名称
            ids: ID 列表

        Returns:
            数据列表
        """
        from pymilvus import Collection

        collection_name = collection_name or self.collection_name
        collection = Collection(collection_name)

        id_list = ", ".join([f'"{id}"' for id in ids])
        expr = f"id in [{id_list}]"
        results = collection.query(expr, output_fields=["*"])

        return results

    def delete(self, collection_name: Optional[str] = None, filter_expr: Optional[str] = None) -> None:
        """删除数据

        Args:
            collection_name: 集合名称
            filter_expr: 过滤表达式
        """
        from pymilvus import Collection

        collection_name = collection_name or self.collection_name
        collection = Collection(collection_name)

        collection.delete(filter_expr)
        collection.flush()
        logger.info(f"从集合 {collection_name} 删除数据：{filter_expr}")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
