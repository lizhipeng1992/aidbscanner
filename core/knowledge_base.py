"""Knowledge base for managing semantic data storage and retrieval"""
import logging
from typing import List, Optional, Dict, Any

from .models import FieldSemantic, TableSemantic, Relationship
from .vector_store import MilvusVectorStore
from .embedding import BaseEmbeddingService, OllamaEmbeddingService, OpenAIEmbeddingService
from config.settings import settings

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """Knowledge base for managing vectorized storage and retrieval of semantic data"""

    def __init__(
        self,
        vector_store: Optional[MilvusVectorStore] = None,
        embedding_service: Optional[BaseEmbeddingService] = None,
    ):
        """Initialize knowledge base

        Args:
            vector_store: Vector storage instance
            embedding_service: Embedding service instance
        """
        self.vector_store = vector_store or MilvusVectorStore(
            host=settings.milvus_host,
            port=settings.milvus_port,
            collection=None,
            vector_dim=settings.milvus_vector_dim,
        )

        # Create embedding service based on configuration
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
        """Connect to vector database"""
        self.vector_store.connect()
        # Migration: drop old collection
        if self.vector_store.has_collection("db_semantics"):
            self.vector_store.drop_collection("db_semantics")
            logger.info("Migration: dropped old collection db_semantics")
        # Create two new collections
        self.vector_store.create_collection(
            collection_name=settings.milvus_table_collection,
            dimension=settings.milvus_vector_dim,
        )
        self.vector_store.create_collection(
            collection_name=settings.milvus_field_collection,
            dimension=settings.milvus_vector_dim,
        )

    def disconnect(self) -> None:
        """Disconnect"""
        self.vector_store.disconnect()

    def store_field_semantic(self, field: FieldSemantic) -> None:
        """Store field semantic information.

        Args:
            field: Field semantic object
        """
        try:
            # Build text for embedding
            text = self._build_field_text(field)

            # Generate vector
            vector = self.embedding_service.embed_text(text)

            # Prepare data
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

            # Insert into vector database
            self.vector_store.insert(
                collection_name=settings.milvus_field_collection,
                vectors=[vector],
                data=data,
            )
            logger.info(f"Stored field semantic: {field.id}")

        except Exception as e:
            logger.error(f"Failed to store field semantic: {e}")

    def store_table_semantic(self, table: TableSemantic) -> None:
        """Store table semantic information.

        Args:
            table: Table semantic object
        """
        # Store table-level semantics to table_semantics
        try:
            text = f"Table: {table.table_name} Chinese Name: {table.chinese_name or ''} Definition: {table.business_definition or ''}"
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
            logger.info(f"Stored table semantic: {table.table_name}")

        except Exception as e:
            logger.error(f"Failed to store table semantic: {e}")

        # Store field-level semantics
        for field in table.field_semantics:
            self.store_field_semantic(field)

    def search_similar_fields(
        self,
        query: str,
        db_name: Optional[str] = None,
        table_name: Optional[str] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search for similar fields.

        Args:
            query: Query text
            db_name: Database name filter (optional)
            table_name: Table name filter (optional)
            top_k: Number of results to return

        Returns:
            Search results list
        """
        try:
            # Generate query vector
            query_vector = self.embedding_service.embed_text(query)

            # Build filter expression
            filter_expr = None
            if db_name:
                filter_expr = f'db_name == "{db_name}"'
            if table_name:
                if filter_expr:
                    filter_expr += f' and table_name == "{table_name}"'
                else:
                    filter_expr = f'table_name == "{table_name}"'

            # Search table collection (priority)
            table_results = self.vector_store.search(
                collection_name=settings.milvus_table_collection,
                query_vector=query_vector,
                top_k=top_k,
                filter_expr=filter_expr,
            )

            # Search field collection
            field_results = self.vector_store.search(
                collection_name=settings.milvus_field_collection,
                query_vector=query_vector,
                top_k=top_k,
                filter_expr=filter_expr,
            )

            # Merge: table results first, deduplicate by id
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
            logger.error(f"Failed to search similar fields: {e}")
            return []

    def get_fields_by_table(
        self, db_name: str, table_name: str
    ) -> List[Dict[str, Any]]:
        """Get all field semantics for a specified table.

        Args:
            db_name: Database name
            table_name: Table name

        Returns:
            Field semantics list
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
            logger.error(f"Failed to get table fields: {e}")
            return []

    def _build_field_text(self, field: FieldSemantic) -> str:
        """Build text for field embedding.

        Args:
            field: Field semantic object

        Returns:
            Text for embedding
        """
        parts = [
            f"Field: {field.column_name}",
            f"Table: {field.table_name}",
            f"Type: {field.data_type}",
        ]

        if field.chinese_name:
            parts.append(f"Chinese Name: {field.chinese_name}")
        if field.business_definition:
            parts.append(f"Business Definition: {field.business_definition}")
        if field.value_rules:
            parts.append(f"Value Rules: {field.value_rules}")
        if field.data_category:
            parts.append(f"Data Category: {field.data_category.value}")

        return " ".join(parts)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
