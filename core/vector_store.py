"""Milvus vector database storage interface"""
import logging
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod

from .models import FieldSemantic, TableSemantic, Relationship

logger = logging.getLogger(__name__)


class BaseVectorStore(ABC):
    """Base class for vector storage"""

    @abstractmethod
    def connect(self) -> None:
        """Connect to vector database"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect"""
        pass

    @abstractmethod
    def create_collection(self, collection_name: str, dimension: int) -> None:
        """Create collection (table)"""
        pass

    @abstractmethod
    def drop_collection(self, collection_name: str) -> None:
        """Drop collection"""
        pass

    @abstractmethod
    def has_collection(self, collection_name: str) -> bool:
        """Check if collection exists"""
        pass

    @abstractmethod
    def insert(self, collection_name: str, vectors: List[List[float]], data: List[Dict[str, Any]]) -> None:
        """Insert vector data"""
        pass

    @abstractmethod
    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 10,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors"""
        pass

    @abstractmethod
    def get(self, collection_name: str, ids: List[str]) -> List[Dict[str, Any]]:
        """Get data by ID"""
        pass

    @abstractmethod
    def delete(self, collection_name: str, filter_expr: str) -> None:
        """Delete data"""
        pass


class MilvusVectorStore(BaseVectorStore):
    """Milvus vector database implementation"""

    def __init__(self, host: str, port: int, collection: Optional[str] = None, vector_dim: int = 1024):
        """Initialize Milvus vector storage

        Args:
            host: Milvus host address
            port: Milvus port
            collection: Collection name
            vector_dim: Vector dimension
        """
        self.host = host
        self.port = port
        self.collection_name = collection
        self.vector_dim = vector_dim
        self._client = None
        self._connected = False

    def connect(self) -> None:
        """Connect to Milvus"""
        if self._connected:
            return

        try:
            from pymilvus import connections, utility

            # Connect to Milvus
            connections.connect(
                alias="default",
                host=self.host,
                port=self.port,
            )

            # Check connection status
            if utility.has_connection("default"):
                self._connected = True
                logger.info(f"Successfully connected to Milvus: {self.host}:{self.port}")
            else:
                raise ConnectionError("Cannot connect to Milvus")

        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise

    def disconnect(self) -> None:
        """Disconnect"""
        if not self._connected:
            return

        try:
            from pymilvus import connections

            connections.disconnect("default")
            self._connected = False
            logger.info("Milvus connection disconnected")
        except Exception as e:
            logger.error(f"Failed to disconnect from Milvus: {e}")

    def create_collection(self, collection_name: Optional[str] = None, dimension: Optional[int] = None) -> None:
        """Create collection.

        Args:
            collection_name: Collection name, defaults to initialized name
            dimension: Vector dimension, defaults to initialized dimension
        """
        from pymilvus import FieldSchema, CollectionSchema, DataType, Collection

        collection_name = collection_name or self.collection_name
        dimension = dimension or self.vector_dim

        # Check if collection already exists
        if self.has_collection(collection_name):
            logger.info(f"Collection {collection_name} already exists, skipping creation")
            return

        # Define fields
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

        schema = CollectionSchema(fields, "Semantic metadata collection")

        # Create collection
        collection = Collection(collection_name, schema)
        logger.info(f"Created collection: {collection_name}")

        # Create vector index
        index_params = {
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {"M": 8, "efConstruction": 200},
        }
        collection.create_index("vector", index_params)
        logger.info(f"Created vector index for collection {collection_name}")

    def drop_collection(self, collection_name: Optional[str] = None) -> None:
        """Drop collection"""
        from pymilvus import utility

        collection_name = collection_name or self.collection_name

        if self.has_collection(collection_name):
            utility.drop_collection(collection_name)
            logger.info(f"Dropped collection: {collection_name}")

    def has_collection(self, collection_name: Optional[str] = None) -> bool:
        """Check if collection exists"""
        from pymilvus import utility

        collection_name = collection_name or self.collection_name
        return utility.has_collection(collection_name)

    def insert(
        self,
        collection_name: Optional[str] = None,
        vectors: Optional[List[List[float]]] = None,
        data: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Insert vector data.

        Args:
            collection_name: Collection name
            vectors: Vector list
            data: Data list, each element is a dict of field values
        """
        from pymilvus import Collection

        collection_name = collection_name or self.collection_name
        collection = Collection(collection_name)

        # Prepare insertion data
        entities = []
        for field in collection.schema.fields:
            if field.name == "vector":
                entities.extend(vectors)
            else:
                field_data = [item.get(field.name, "") for item in data]
                entities.extend(field_data)

        collection.insert(entities)
        collection.flush()
        logger.info(f"Inserted {len(vectors)} records into collection {collection_name}")

    def search(
        self,
        collection_name: Optional[str] = None,
        query_vector: Optional[List[float]] = None,
        top_k: int = 10,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors.

        Args:
            collection_name: Collection name
            query_vector: Query vector
            top_k: Number of results to return
            filter_expr: Filter expression

        Returns:
            Search results list
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

        # Parse search results
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
        """Get data by ID.

        Args:
            collection_name: Collection name
            ids: ID list

        Returns:
            Data list
        """
        from pymilvus import Collection

        collection_name = collection_name or self.collection_name
        collection = Collection(collection_name)

        id_list = ", ".join([f'"{id}"' for id in ids])
        expr = f"id in [{id_list}]"
        results = collection.query(expr, output_fields=["*"])

        return results

    def delete(self, collection_name: Optional[str] = None, filter_expr: Optional[str] = None) -> None:
        """Delete data.

        Args:
            collection_name: Collection name
            filter_expr: Filter expression
        """
        from pymilvus import Collection

        collection_name = collection_name or self.collection_name
        collection = Collection(collection_name)

        collection.delete(filter_expr)
        collection.flush()
        logger.info(f"Deleted data from collection {collection_name}: {filter_expr}")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
