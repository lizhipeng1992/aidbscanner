"""ChromaDB storage module"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from chromadb import PersistentClient
from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

from .models import TableSemantic, FieldSemantic

logger = logging.getLogger(__name__)


class ChromaStore:
    """ChromaDB storage for persisting semantic analysis results"""

    def __init__(self, path: str = "./data/chroma"):
        """Initialize ChromaDB storage

        Args:
            path: ChromaDB persistent storage path
        """
        self.path = path
        self.client = PersistentClient(path)
        self.collection = self.client.get_or_create_collection(
            name="semantics",
            metadata={"description": "Database semantic metadata"},
            embedding_function=ONNXMiniLM_L6_V2(),
        )
        logger.debug(f"ChromaDB initialization complete, storage path: {path}")

    def store_table_semantic(self, table_semantic: TableSemantic) -> str:
        """Store table semantic information

        Args:
            table_semantic: Table semantic object

        Returns:
            Table name
        """
        db_name = table_semantic.db_name
        table_name = table_semantic.table_name

        # Store each field as an independent document
        ids = []
        documents = []
        metadata_list = []

        for field in table_semantic.field_semantics:
            field_id = f"{db_name}.{table_name}.{field.column_name}"
            ids.append(field_id)

            meta = {
                "db_name": db_name,
                "table_name": table_name,
                "column_name": field.column_name,
                "data_type": field.data_type,
                "chinese_name": field.chinese_name,
                "business_definition": field.business_definition,
                "value_rules": field.value_rules,
                "data_category": field.data_category.value if hasattr(field.data_category, "value") else str(field.data_category),
                "status": field.status.value if hasattr(field.status, "value") else str(field.status),
                "calibrated_by": field.calibrated_by,
                "calibrated_at": field.calibrated_at.isoformat() if field.calibrated_at else None,
                "created_at": field.created_at.isoformat() if field.created_at else None,
                "updated_at": field.updated_at.isoformat() if field.updated_at else None,
                "table_chinese_name": table_semantic.chinese_name,
                "table_business_definition": table_semantic.business_definition,
                "table_data_category": table_semantic.data_category.value if hasattr(table_semantic.data_category, "value") else str(table_semantic.data_category),
            }
            # ChromaDB requires list metadata values to be non-empty
            if field.related_fields:
                meta["related_fields"] = field.related_fields
            metadata_list.append(meta)

            # Build embedding text (ChromaDB will automatically use ONNXMiniLM_L6_V2 for vector generation)
            text_parts = [
                f"字段：{field.column_name}",
                f"表：{field.table_name}",
                f"类型：{field.data_type}",
            ]
            if field.chinese_name:
                text_parts.append(f"中文名称：{field.chinese_name}")
            if field.business_definition:
                text_parts.append(f"业务定义：{field.business_definition}")
            if field.value_rules:
                text_parts.append(f"取值规则：{field.value_rules}")
            if field.data_category:
                text_parts.append(f"数据分类：{field.data_category.value}")
            documents.append(" ".join(text_parts))

        # Batch add to ChromaDB (automatic embedding)
        if ids:
            kwargs: Dict[str, Any] = {"ids": ids, "documents": documents, "metadatas": metadata_list}
            self.collection.upsert(**kwargs)
            logger.info(f"Stored table semantics to ChromaDB: {table_name} ({len(ids)} fields)")

        return table_name

    def get_table_semantic(self, db_name: str, table_name: str) -> Optional[Dict[str, Any]]:
        """Get table semantic information

        Args:
            db_name: Database name
            table_name: Table name

        Returns:
            Table semantic data, or None if not found
        """
        try:
            results = self.collection.get(
                where={"$and": [{"db_name": db_name}, {"table_name": table_name}]}
            )

            if not results.get("ids"):
                return None

            # ChromaDB returns metadatas (plural)
            metadata_list = results.get("metadatas", [])

            # Build table semantic data structure
            fields = []
            for i, doc_id in enumerate(results.get("ids", [])):
                meta = metadata_list[i] if i < len(metadata_list) else {}
                fields.append({
                    "column_name": meta.get("column_name"),
                    "data_type": meta.get("data_type"),
                    "chinese_name": meta.get("chinese_name"),
                    "business_definition": meta.get("business_definition"),
                    "value_rules": meta.get("value_rules"),
                    "related_fields": meta.get("related_fields", []),
                    "data_category": meta.get("data_category"),
                    "status": meta.get("status"),
                    "calibrated_by": meta.get("calibrated_by"),
                    "calibrated_at": meta.get("calibrated_at"),
                    "created_at": meta.get("created_at"),
                    "updated_at": meta.get("updated_at"),
                })

            # Get table-level metadata (extracted from first field)
            first_meta = metadata_list[0] if metadata_list else {}

            return {
                "table_name": table_name,
                "db_name": db_name,
                "chinese_name": first_meta.get("table_chinese_name", table_name),
                "business_definition": first_meta.get("table_business_definition", ""),
                "data_category": first_meta.get("table_data_category", "fact"),
                "fields": fields,
                "updated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to read table semantic: {e}")
            return None

    def get_index(self) -> List[Dict[str, Any]]:
        """Get global index

        Returns:
            Index entry list (grouped by table)
        """
        try:
            results = self.collection.get(include=[])
            ids = results.get("ids", [])
            metadata_list = results.get("metadatas", [])

            # Group by table
            tables = {}
            for i, doc_id in enumerate(ids):
                meta = metadata_list[i] if i < len(metadata_list) else {}
                db_name = meta.get("db_name")
                table_name = meta.get("table_name")
                key = f"{db_name}/{table_name}"

                if key not in tables:
                    tables[key] = {
                        "db_name": db_name,
                        "table_name": table_name,
                        "chinese_name": meta.get("table_chinese_name", table_name),
                        "business_definition": meta.get("table_business_definition", ""),
                        "fields": [],
                        "file_path": key,
                    }
                tables[key]["fields"].append(meta.get("column_name"))

            return list(tables.values())
        except Exception as e:
            logger.error(f"Failed to get index: {e}")
            return []

    def search_tables(self, keyword: str) -> List[Dict[str, Any]]:
        """Search tables by keyword

        Args:
            keyword: Search keyword

        Returns:
            Matching table list
        """
        entries = self.get_index()
        results = []

        for entry in entries:
            if (
                keyword.lower() in entry.get("table_name", "").lower()
                or keyword.lower() in entry.get("chinese_name", "").lower()
                or keyword.lower() in entry.get("business_definition", "").lower()
            ):
                results.append(entry)

        return results

    def list_tables_by_db(self, db_name: str) -> List[Dict[str, Any]]:
        """List all tables in a specified database

        Args:
            db_name: Database name

        Returns:
            Table list
        """
        entries = self.get_index()
        return [e for e in entries if e.get("db_name") == db_name]

    def get_pending_fields(self, db_name: str = None) -> List[Dict[str, Any]]:
        """Get pending field review list

        Args:
            db_name: Optional database name filter

        Returns:
            Pending field review list
        """
        try:
            where_conditions = [{"status": "pending"}]
            if db_name:
                where_conditions.append({"db_name": db_name})

            where = {"$and": where_conditions} if len(where_conditions) > 1 else where_conditions[0]

            results = self.collection.get(where=where)
            metadata_list = results.get("metadatas", [])

            pending_fields = []
            for i, doc_id in enumerate(results.get("ids", [])):
                meta = metadata_list[i] if i < len(metadata_list) else {}
                pending_fields.append({
                    "field_id": doc_id,
                    "db_name": meta.get("db_name"),
                    "table_name": meta.get("table_name"),
                    "column_name": meta.get("column_name"),
                    "data_type": meta.get("data_type"),
                    "chinese_name": meta.get("chinese_name"),
                    "business_definition": meta.get("business_definition"),
                    "value_rules": meta.get("value_rules"),
                    "related_fields": meta.get("related_fields", []),
                    "data_category": meta.get("data_category"),
                    "created_at": meta.get("created_at"),
                })
            return pending_fields
        except Exception as e:
            logger.error(f"Failed to get pending fields: {e}")
            return []

    def submit_field(self, field_id: str, calibrated_by: str, modifications: Dict[str, Any] = None) -> bool:
        """Submit review (confirm field)

        Args:
            field_id: Field unique identifier (db_name.table_name.column_name)
            calibrated_by: Reviewer
            modifications: Optional modifications

        Returns:
            Whether successful
        """
        try:
            # Build update content
            updates = {
                "status": "calibrated",
                "calibrated_by": calibrated_by,
                "calibrated_at": datetime.now().isoformat(),
            }

            if modifications:
                for key, value in modifications.items():
                    if key in ["chinese_name", "business_definition", "value_rules", "data_category"]:
                        updates[key] = value

            # Update field
            self.collection.update(ids=[field_id], metadatas=[updates])
            logger.info(f"Review submission successful: {field_id}")
            return True
        except Exception as e:
            logger.error(f"Review submission failed: {e}")
            return False

    def reject_field(self, field_id: str) -> bool:
        """Reject field

        Args:
            field_id: Field unique identifier (db_name.table_name.column_name)

        Returns:
            Whether successful
        """
        try:
            self.collection.update(
                ids=[field_id],
                metadatas=[{"status": "skipped", "updated_at": datetime.now().isoformat()}]
            )
            logger.info(f"Field rejected successfully: {field_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to reject field: {e}")
            return False

    def modify_field(self, field_id: str, modifications: Dict[str, Any], calibrated_by: str) -> bool:
        """Modify field and confirm

        Args:
            field_id: Field unique identifier (db_name.table_name.column_name)
            modifications: Modifications
            calibrated_by: Modifier

        Returns:
            Whether successful
        """
        return self.submit_field(field_id, calibrated_by, modifications)

    def search_fields(
        self,
        query: str,
        db_name: Optional[str] = None,
        table_name: Optional[str] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Field search based on vector similarity

        Args:
            query: Query text
            db_name: Database name filter (optional)
            table_name: Table name filter (optional)
            top_k: Number of results to return

        Returns:
            Search results list, each containing metadata and distance
        """
        try:
            where_conditions: List[Dict[str, Any]] = []
            if db_name:
                where_conditions.append({"db_name": db_name})
            if table_name:
                where_conditions.append({"table_name": table_name})

            kwargs: Dict[str, Any] = {
                "query_texts": [query],
                "n_results": top_k,
                "include": ["metadatas", "distances"],
            }
            if where_conditions:
                kwargs["where"] = {"$and": where_conditions} if len(where_conditions) > 1 else where_conditions[0]

            results = self.collection.query(**kwargs)
            return self._parse_query_results(results)

        except Exception as e:
            logger.error(f"Vector search for fields failed: {e}")
            return []

    def search_tables_vector(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Table search based on vector similarity

        Args:
            query: Query text
            top_k: Number of results to return

        Returns:
            Search results list
        """
        try:
            kwargs: Dict[str, Any] = {
                "query_texts": [query],
                "n_results": top_k,
                "include": ["metadatas", "distances"],
            }

            results = self.collection.query(**kwargs)
            parsed = self._parse_query_results(results)

            # Deduplicate by table, keeping table-level info
            seen = set()
            unique_results = []
            for item in parsed:
                meta = item.get("metadata", {})
                table_key = f"{meta.get('db_name')}.{meta.get('table_name')}"
                if table_key not in seen:
                    seen.add(table_key)
                    unique_results.append(item)

            return unique_results

        except Exception as e:
            logger.error(f"Vector table search failed: {e}")
            return []

    def _parse_query_results(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse ChromaDB query results into unified format"""
        items = []
        metadatas = results.get("metadatas", [])
        distances = results.get("distances", [])

        for i, meta_list in enumerate(metadatas):
            for j, meta in enumerate(meta_list):
                distance = distances[i][j] if distances and i < len(distances) and j < len(distances[i]) else 0.0
                # ChromaDB distance: smaller means more similar, convert to similarity score
                score = 1.0 - distance if distance < 1.0 else 0.0
                items.append({
                    "metadata": meta,
                    "distance": distance,
                    "score": score,
                })

        return items
