"""ChromaDB 存储模块"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from chromadb import PersistentClient
from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

from .models import TableSemantic, FieldSemantic

logger = logging.getLogger(__name__)


class ChromaStore:
    """ChromaDB 存储，用于持久化语义分析结果"""

    def __init__(self, path: str = "./data/chroma"):
        """初始化 ChromaDB 存储

        Args:
            path: ChromaDB 持久化存储路径
        """
        self.path = path
        self.client = PersistentClient(path)
        self.collection = self.client.get_or_create_collection(
            name="semantics",
            metadata={"description": "Database semantic metadata"},
            embedding_function=ONNXMiniLM_L6_V2(),
        )
        logger.debug(f"ChromaDB 初始化完成，存储路径：{path}")

    def store_table_semantic(self, table_semantic: TableSemantic) -> str:
        """存储表语义信息

        Args:
            table_semantic: 表语义对象

        Returns:
            表名
        """
        db_name = table_semantic.db_name
        table_name = table_semantic.table_name

        # 存储每个字段作为独立的文档
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

            # 构建嵌入文本（ChromaDB 会自动使用 ONNXMiniLM_L6_V2 生成向量）
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

        # 批量添加到 ChromaDB（自动嵌入）
        if ids:
            kwargs: Dict[str, Any] = {"ids": ids, "documents": documents, "metadatas": metadata_list}
            self.collection.upsert(**kwargs)
            logger.info(f"存储表语义到 ChromaDB: {table_name} ({len(ids)} 个字段)")

        return table_name

    def get_table_semantic(self, db_name: str, table_name: str) -> Optional[Dict[str, Any]]:
        """获取表语义信息

        Args:
            db_name: 数据库名
            table_name: 表名

        Returns:
            表语义数据，不存在则返回 None
        """
        try:
            results = self.collection.get(
                where={"db_name": db_name, "table_name": table_name}
            )

            if not results.get("ids"):
                return None

            # 构建表语义数据结构
            fields = []
            for i, doc_id in enumerate(results.get("ids", [])):
                meta = results["metadata"][i]
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

            # 获取表级元数据（从第一个字段中提取）
            first_meta = results["metadata"][0] if results.get("metadata") else {}

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
            logger.error(f"读取表语义失败：{e}")
            return None

    def get_index(self) -> List[Dict[str, Any]]:
        """获取全局索引

        Returns:
            索引条目列表（按表分组）
        """
        try:
            results = self.collection.get(include=[])
            ids = results.get("ids", [])
            metadata_list = results.get("metadata", [])

            # 按表分组
            tables = {}
            for i, doc_id in enumerate(ids):
                meta = metadata_list[i]
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
            logger.error(f"获取索引失败：{e}")
            return []

    def search_tables(self, keyword: str) -> List[Dict[str, Any]]:
        """根据关键词搜索表

        Args:
            keyword: 搜索关键词

        Returns:
            匹配的表列表
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
        """列出指定数据库的所有表

        Args:
            db_name: 数据库名

        Returns:
            表列表
        """
        entries = self.get_index()
        return [e for e in entries if e.get("db_name") == db_name]

    def get_pending_fields(self, db_name: str = None) -> List[Dict[str, Any]]:
        """获取待审核字段列表

        Args:
            db_name: 可选的数据库名过滤

        Returns:
            待审核字段列表
        """
        try:
            where = {"status": "pending"}
            if db_name:
                where["db_name"] = db_name

            results = self.collection.get(where=where)

            pending_fields = []
            for i, doc_id in enumerate(results.get("ids", [])):
                meta = results["metadata"][i]
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
            logger.error(f"获取待审核字段失败：{e}")
            return []

    def submit_field(self, field_id: str, calibrated_by: str, modifications: Dict[str, Any] = None) -> bool:
        """提交审核（确认字段）

        Args:
            field_id: 字段唯一标识 (db_name.table_name.column_name)
            calibrated_by: 审核人
            modifications: 可选的修改内容

        Returns:
            是否成功
        """
        try:
            # 构建更新内容
            updates = {
                "status": "calibrated",
                "calibrated_by": calibrated_by,
                "calibrated_at": datetime.now().isoformat(),
            }

            if modifications:
                for key, value in modifications.items():
                    if key in ["chinese_name", "business_definition", "value_rules", "data_category"]:
                        updates[key] = value

            # 更新字段
            self.collection.update(ids=[field_id], metadata=[updates])
            logger.info(f"提交审核成功：{field_id}")
            return True
        except Exception as e:
            logger.error(f"提交审核失败：{e}")
            return False

    def reject_field(self, field_id: str) -> bool:
        """拒绝字段

        Args:
            field_id: 字段唯一标识 (db_name.table_name.column_name)

        Returns:
            是否成功
        """
        try:
            self.collection.update(
                ids=[field_id],
                metadata=[{"status": "skipped", "updated_at": datetime.now().isoformat()}]
            )
            logger.info(f"拒绝字段成功：{field_id}")
            return True
        except Exception as e:
            logger.error(f"拒绝字段失败：{e}")
            return False

    def modify_field(self, field_id: str, modifications: Dict[str, Any], calibrated_by: str) -> bool:
        """修改字段并确认

        Args:
            field_id: 字段唯一标识 (db_name.table_name.column_name)
            modifications: 修改内容
            calibrated_by: 修改人

        Returns:
            是否成功
        """
        return self.submit_field(field_id, calibrated_by, modifications)

    def search_fields(
        self,
        query: str,
        db_name: Optional[str] = None,
        table_name: Optional[str] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """基于向量相似度的字段搜索

        Args:
            query: 查询文本
            db_name: 数据库名过滤（可选）
            table_name: 表名过滤（可选）
            top_k: 返回结果数量

        Returns:
            搜索结果列表，每项包含 metadata 和 distance
        """
        try:
            where_filter: Dict[str, Any] = {}
            if db_name:
                where_filter["db_name"] = db_name
            if table_name:
                where_filter["table_name"] = table_name

            kwargs: Dict[str, Any] = {
                "query_texts": [query],
                "n_results": top_k,
                "include": ["metadatas", "distances"],
            }
            if where_filter:
                kwargs["where"] = where_filter

            results = self.collection.query(**kwargs)
            return self._parse_query_results(results)

        except Exception as e:
            logger.error(f"向量搜索字段失败：{e}")
            return []

    def search_tables_vector(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """基于向量相似度的表搜索

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            搜索结果列表
        """
        try:
            kwargs: Dict[str, Any] = {
                "query_texts": [query],
                "n_results": top_k,
                "include": ["metadatas", "distances"],
            }

            results = self.collection.query(**kwargs)
            parsed = self._parse_query_results(results)

            # 按表去重，保留表级信息
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
            logger.error(f"向量搜索表失败：{e}")
            return []

    def _parse_query_results(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析 ChromaDB 查询结果为统一格式"""
        items = []
        metadatas = results.get("metadatas", [])
        distances = results.get("distances", [])

        for i, meta_list in enumerate(metadatas):
            for j, meta in enumerate(meta_list):
                distance = distances[i][j] if distances and i < len(distances) and j < len(distances[i]) else 0.0
                # ChromaDB distance 越小越相似，转换为相似度分数
                score = 1.0 - distance if distance < 1.0 else 0.0
                items.append({
                    "metadata": meta,
                    "distance": distance,
                    "score": score,
                })

        return items
