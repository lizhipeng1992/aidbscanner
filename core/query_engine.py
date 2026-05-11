"""RAG 查询引擎，统一处理自然语言查询"""
import logging
from typing import List, Optional, Dict, Any

from config.settings import settings
from core.models import FieldSemantic, TableSemantic, Relationship, RAGContext, ColumnType, DataCategory
from core.llm_client import (
    LLMProvider,
    create_llm_client,
    ChatMessage,
    BaseLLMClient,
)
from core.knowledge_base import KnowledgeBase
from core.chroma_store import ChromaStore

logger = logging.getLogger(__name__)


class QueryResult:
    """Query result wrapper"""

    def __init__(
        self,
        question: str,
        answer: str,
        relevant_fields: List[Dict[str, Any]] = None,
        relevant_tables: List[Dict[str, Any]] = None,
        has_error: bool = False,
        error_message: Optional[str] = None,
    ):
        self.question = question
        self.answer = answer
        self.relevant_fields = relevant_fields or []
        self.relevant_tables = relevant_tables or []
        self.has_error = has_error
        self.error_message = error_message

    @property
    def fields(self) -> List[Dict[str, Any]]:
        return self.relevant_fields

    @property
    def tables(self) -> List[Dict[str, Any]]:
        return self.relevant_tables


class QueryEngine:
    """RAG 查询引擎，支持 Milvus 和 ChromaDB 两种后端"""

    SYSTEM_PROMPT = (
        "你是一个数据库语义查询助手。基于提供的数据库语义元数据，"
        "用中文回答用户的自然语言问题。"
        "如果提供的元数据不足以回答问题，请明确说明。"
        "回答应简洁、准确，直接回应用户的问题。"
    )

    def __init__(
        self,
        storage: Optional[Any] = None,
        knowledge_base: Optional[KnowledgeBase] = None,
        llm_client: Optional[BaseLLMClient] = None,
    ):
        self._storage = storage
        self._knowledge_base = knowledge_base
        self._llm_client = llm_client
        self._storage_type = settings.semantic_storage_type

    @property
    def storage(self) -> Optional[ChromaStore]:
        if self._storage is None:
            self._storage = ChromaStore(settings.semantic_storage_path)
        return self._storage

    @property
    def knowledge_base(self) -> Optional[KnowledgeBase]:
        if self._knowledge_base is None and self._storage_type == "milvus":
            self._knowledge_base = KnowledgeBase()
            self._knowledge_base.connect()
        return self._knowledge_base

    @property
    def llm_client(self) -> BaseLLMClient:
        if self._llm_client is None:
            provider = settings.llm_provider
            if provider == LLMProvider.OLLAMA:
                self._llm_client = create_llm_client(LLMProvider.OLLAMA, {
                    "host": settings.ollama_host,
                    "model": settings.ollama_model,
                })
            else:
                self._llm_client = create_llm_client(LLMProvider.OPENAI, {
                    "base_url": settings.openai_base_url,
                    "api_key": settings.openai_api_key,
                    "model": settings.openai_model,
                })
        return self._llm_client

    def query(self, question: str, db_name: Optional[str] = None, top_k: int = 10) -> QueryResult:
        """Execute natural language query

        Args:
            question: Natural language question
            db_name: Optional database name filter
            top_k: Number of retrieval results

        Returns:
            QueryResult containing answer and retrieval results
        """
        try:
            # 检索相关字段和表
            search_results = self._retrieve(question, db_name, top_k)

            # 构建 RAG 上下文
            rag_context = self._build_rag_context(question, search_results)

            # 生成答案
            answer = self._generate_answer(rag_context)

            return QueryResult(
                question=question,
                answer=answer,
                relevant_fields=search_results.get("fields", []),
                relevant_tables=search_results.get("tables", []),
            )
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return QueryResult(
                question=question,
                answer=f"An error occurred during query: {str(e)}",
                has_error=True,
                error_message=str(e),
            )

    def _retrieve(self, question: str, db_name: Optional[str], top_k: int) -> Dict[str, Any]:
        """Execute retrieval based on storage backend type"""
        result: Dict[str, Any] = {"fields": [], "tables": []}

        if self._storage_type == "milvus":
            result = self._retrieve_milvus(question, db_name, top_k)
        elif self._storage_type == "chroma":
            result = self._retrieve_chroma(question, db_name, top_k)
        else:
            # No storage backend, try ChromaStore as default
            result = self._retrieve_chroma(question, db_name, top_k)

        return result

    def _retrieve_milvus(self, question: str, db_name: Optional[str], top_k: int) -> Dict[str, Any]:
        """Milvus backend retrieval"""
        result: Dict[str, Any] = {"fields": [], "tables": []}

        kb = self.knowledge_base
        if kb is None:
            return result

        try:
            # 搜索表集合和字段集合
            search_results = kb.search_similar_fields(
                query=question,
                db_name=db_name,
                top_k=top_k * 2,
            )

            for item in search_results:
                column_name = item.get("column_name", "")
                if not column_name:
                    # 表级记录（来自 table_semantics）
                    result["tables"].append({
                        "table_name": item.get("table_name", ""),
                        "db_name": item.get("db_name", ""),
                        "chinese_name": item.get("chinese_name", ""),
                        "business_definition": item.get("business_definition", ""),
                        "data_category": item.get("data_category", "fact"),
                    })
                else:
                    # 字段级记录（来自 field_semantics）
                    result["fields"].append({
                        "column_name": column_name,
                        "table_name": item.get("table_name", ""),
                        "db_name": item.get("db_name", ""),
                        "data_type": item.get("data_type", ""),
                        "chinese_name": item.get("chinese_name", ""),
                        "business_definition": item.get("business_definition", ""),
                        "value_rules": item.get("value_rules", ""),
                        "data_category": item.get("data_category", "other"),
                    })

        except Exception as e:
            logger.error(f"Milvus retrieval failed: {e}")

        return result

    def _retrieve_chroma(self, question: str, db_name: Optional[str], top_k: int) -> Dict[str, Any]:
        """ChromaDB backend retrieval"""
        result: Dict[str, Any] = {"fields": [], "tables": []}

        try:
            # 搜索相似字段
            field_results = self.storage.search_fields(
                query=question,
                db_name=db_name,
                top_k=top_k,
            )

            for item in field_results:
                meta = item.get("metadata", {})
                result["fields"].append({
                    "column_name": meta.get("column_name", ""),
                    "table_name": meta.get("table_name", ""),
                    "db_name": meta.get("db_name", ""),
                    "data_type": meta.get("data_type", ""),
                    "chinese_name": meta.get("chinese_name", ""),
                    "business_definition": meta.get("business_definition", ""),
                    "value_rules": meta.get("value_rules", ""),
                    "data_category": meta.get("data_category", "other"),
                    "relevance_score": item.get("score", 0.0),
                })

            # 搜索相关表（去重）
            seen_tables = set()
            for field in result["fields"]:
                table_key = f"{field['db_name']}.{field['table_name']}"
                if table_key not in seen_tables:
                    seen_tables.add(table_key)
                    result["tables"].append({
                        "table_name": field["table_name"],
                        "db_name": field["db_name"],
                        "chinese_name": meta.get("table_chinese_name", field["table_name"]) if (meta := field_results[0].get("metadata", {})) else field["table_name"],
                        "business_definition": meta.get("table_business_definition", "") if (meta := field_results[0].get("metadata", {})) else "",
                        "data_category": meta.get("table_data_category", "fact") if (meta := field_results[0].get("metadata", {})) else "fact",
                        "relevance_score": field.get("relevance_score", 0.0),
                    })

        except Exception as e:
            logger.error(f"ChromaDB retrieval failed: {e}")

        return result

    def _build_rag_context(self, question: str, search_results: Dict[str, Any]) -> RAGContext:
        """Build RAG context from search results"""
        fields = []
        for item in search_results.get("fields", []):
            fields.append(FieldSemantic(
                id=f"{item.get('db_name', '')}.{item.get('table_name', '')}.{item.get('column_name', '')}",
                db_name=item.get("db_name", ""),
                table_name=item.get("table_name", ""),
                column_name=item.get("column_name", ""),
                data_type=item.get("data_type", ""),
                chinese_name=item.get("chinese_name"),
                business_definition=item.get("business_definition"),
                value_rules=item.get("value_rules"),
                data_category=DataCategory(item.get("data_category", "other")),
                status=ColumnType.AUTO,
            ))

        tables = []
        for item in search_results.get("tables", []):
            tables.append(TableSemantic(
                table_name=item.get("table_name", ""),
                db_name=item.get("db_name", ""),
                chinese_name=item.get("chinese_name"),
                business_definition=item.get("business_definition"),
                data_category=DataCategory(item.get("data_category", "fact")),
                field_semantics=[f for f in fields if f.table_name == item.get("table_name")],
            ))

        return RAGContext(
            query=question,
            relevant_fields=fields,
            relevant_tables=tables,
        )

    def _generate_answer(self, rag_context: RAGContext) -> str:
        """Generate answer using LLM based on RAG context"""
        prompt = rag_context.to_prompt()

        if not prompt.strip():
            return "No relevant database semantic information found. Please run a scan analysis to store semantic data before querying."

        messages = [
            ChatMessage(role="system", content=self.SYSTEM_PROMPT),
            ChatMessage(role="user", content=f"问题：{rag_context.query}\n\n{prompt}"),
        ]

        try:
            response = self.llm_client.chat(messages)
            return response.content
        except Exception as e:
            logger.error(f"Failed to generate answer with LLM: {e}")
            # Fallback: return retrieved context
            return f"Unable to generate answer ({str(e)}).\n\nRetrieved relevant semantic information:\n{prompt}"
