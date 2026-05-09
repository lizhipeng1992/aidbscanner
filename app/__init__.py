"""FastAPI 应用层"""
import logging
from typing import List, Optional, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from config.settings import settings
from core.scanner import MySQLScanner
from core.semantic_analyzer import SemanticAnalyzer
from core.models import FieldSemantic, ColumnType, DataCategory
from datetime import datetime
from core.chroma_store import ChromaStore
from app.schemas import (
    DatabaseListResponse,
    TableListResponse,
    TableMetadataResponse,
    FieldSemanticRequest,
    FieldSemanticResponse,
    TableSemanticRequest,
    TableSemanticResponse,
    RelationshipResponse,
    RelationshipVerifyRequest,
    HealthResponse,
    ScanRequest,
    ScanProgressResponse,
    # 审核相关
    ReviewPendingResponse,
    ReviewPendingItem,
    ReviewSubmitRequest,
    ReviewRejectRequest,
    ReviewModifyRequest,
    ReviewResultResponse,
    # 查询相关
    QueryRequest,
    QueryResponse,
    QueryFieldResult,
    QueryTableResult,
    # 语义缓存相关
    TableSemanticCacheResponse,
    FieldSemanticCacheResponse,
    UpdateTableSemanticRequest,
    UpdateFieldSemanticRequest,
)

logger = logging.getLogger(__name__)

# ChromaDB 存储实例
chroma_store = ChromaStore(settings.semantic_storage_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时的初始化
    logger.info("AI Database Scanner 启动")
    yield
    # 关闭时的清理
    logger.info("AI Database Scanner 关闭")


app = FastAPI(
    title="AI Database Scanner",
    description="基于本地 LLM 的 MySQL 数据库语义层扫描工具",
    version="1.0.0",
    lifespan=lifespan,
)


def get_scanner() -> MySQLScanner:
    """获取 MySQL 扫描器实例"""
    return MySQLScanner()


def get_analyzer(scanner: Optional[MySQLScanner] = None) -> SemanticAnalyzer:
    """获取语义分析器实例"""
    if scanner is None:
        scanner = get_scanner()
    return SemanticAnalyzer(scanner)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    from core.llm_client import LLMProvider, create_llm_client, ChatMessage

    mysql_status = "unknown"
    llm_status = "unknown"

    # 检查 MySQL 连接
    try:
        scanner = get_scanner()
        scanner.list_databases()
        mysql_status = "connected"
    except Exception as e:
        mysql_status = f"error: {str(e)}"

    # 检查 LLM 连接（根据配置选择）
    try:
        provider = settings.llm_provider
        if provider == LLMProvider.OLLAMA:
            import ollama
            client = ollama.Client(host=settings.ollama_host)
            client.list()
            llm_status = "connected"
        else:
            from openai import OpenAI
            client = OpenAI(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
            )
            # 简单的连接测试
            client.models.list()
            llm_status = "connected"
    except Exception as e:
        llm_status = f"error: {str(e)}"

    return HealthResponse(
        status="healthy",
        mysql=mysql_status,
        llm=llm_status,
        llm_provider=settings.llm_provider.value,
    )


@app.get("/databases", response_model=DatabaseListResponse)
async def list_databases():
    """列出所有数据库"""
    try:
        scanner = get_scanner()
        databases = scanner.list_databases()
        # 过滤系统数据库
        system_dbs = {"information_schema", "mysql", "performance_schema", "sys"}
        databases = [db for db in databases if db not in system_dbs]
        return DatabaseListResponse(databases=databases)
    except Exception as e:
        logger.error(f"获取数据库列表失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/databases/{db_name}/tables", response_model=TableListResponse)
async def list_tables(db_name: str):
    """列出指定数据库的所有表"""
    try:
        scanner = get_scanner()
        tables = scanner.scan_database(db_name)

        if not tables:
            raise HTTPException(status_code=404, detail=f"数据库不存在：{db_name}")

        table_metadata_list = [
            TableMetadataResponse(
                table_name=table.table_name,
                table_comment=table.table_comment,
                engine=table.engine,
                columns=[col.model_dump() for col in table.columns],
            )
            for table in tables
        ]

        return TableListResponse(database=db_name, tables=table_metadata_list)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取表列表失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/fields/analyze", response_model=FieldSemanticResponse)
async def analyze_field(request: FieldSemanticRequest):
    """分析单个字段的语义"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        # 获取表元数据
        tables = scanner.scan_database(request.db_name)
        if not tables:
            raise HTTPException(status_code=404, detail=f"数据库不存在：{request.db_name}")

        target_table = None
        for table in tables:
            if table.table_name == request.table_name:
                target_table = table
                break

        if not target_table:
            raise HTTPException(status_code=404, detail=f"表不存在：{request.table_name}")

        # 查找字段
        target_column = None
        for col in target_table.columns:
            if col.column_name == request.column_name:
                target_column = col
                break

        if not target_column:
            raise HTTPException(status_code=404, detail=f"字段不存在：{request.column_name}")

        # 获取示例数据
        sample_values = scanner.get_sample_data(
            request.db_name, request.table_name, request.column_name
        )

        # 分析字段语义
        field_semantic = analyzer.analyze_field(
            target_column, request.table_name, request.db_name, sample_values
        )

        return FieldSemanticResponse(
            id=field_semantic.id,
            db_name=field_semantic.db_name,
            table_name=field_semantic.table_name,
            column_name=field_semantic.column_name,
            data_type=field_semantic.data_type,
            chinese_name=field_semantic.chinese_name,
            business_definition=field_semantic.business_definition,
            value_rules=field_semantic.value_rules,
            related_fields=field_semantic.related_fields,
            data_category=field_semantic.data_category,
            status=field_semantic.status,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"分析字段语义失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tables/analyze", response_model=TableSemanticResponse)
async def analyze_table(request: TableSemanticRequest):
    """分析整张表的语义"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        # 获取表元数据
        tables = scanner.scan_database(request.db_name)
        if not tables:
            raise HTTPException(status_code=404, detail=f"数据库不存在：{request.db_name}")

        target_table = None
        for table in tables:
            if table.table_name == request.table_name:
                target_table = table
                break

        if not target_table:
            raise HTTPException(status_code=404, detail=f"表不存在：{request.table_name}")

        # 分析表语义
        table_semantic = analyzer.analyze_table(target_table, request.db_name, request.sample_size)

        return TableSemanticResponse(
            table_name=table_semantic.table_name,
            db_name=table_semantic.db_name,
            chinese_name=table_semantic.chinese_name,
            business_definition=table_semantic.business_definition,
            data_category=table_semantic.data_category,
            fields=[
                FieldSemanticResponse(
                    id=fs.id,
                    db_name=fs.db_name,
                    table_name=fs.table_name,
                    column_name=fs.column_name,
                    data_type=fs.data_type,
                    chinese_name=fs.chinese_name,
                    business_definition=fs.business_definition,
                    value_rules=fs.value_rules,
                    related_fields=fs.related_fields,
                    data_category=fs.data_category,
                    status=fs.status,
                )
                for fs in table_semantic.field_semantics
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"分析表语义失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/relationships/verify", response_model=RelationshipResponse)
async def verify_relationship(request: RelationshipVerifyRequest):
    """验证表间关系"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        from core.models import Relationship

        rel = Relationship(
            source_table=request.source_table,
            source_column=request.source_column,
            target_table=request.target_table,
            target_column=request.target_column,
            relationship_type="many-to-one",
            match_rate=0.0,
            verified=False,
        )

        # 计算匹配率
        match_rate = scanner.calculate_match_rate(request.db_name, rel)
        rel.match_rate = match_rate

        # 使用 LLM 验证
        is_valid = analyzer.verify_relationship(rel)
        rel.verified = is_valid

        return RelationshipResponse(
            source_table=rel.source_table,
            source_column=rel.source_column,
            target_table=rel.target_table,
            target_column=rel.target_column,
            relationship_type=rel.relationship_type,
            match_rate=rel.match_rate,
            verified=rel.verified,
        )
    except Exception as e:
        logger.error(f"验证关系失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/discover/relationships", response_model=List[RelationshipResponse])
async def discover_relationships(db_name: str = Query(..., description="数据库名称")):
    """发现潜在的外键关系"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        # 扫描数据库
        tables = scanner.scan_database(db_name)
        if not tables:
            raise HTTPException(status_code=404, detail=f"数据库不存在：{db_name}")

        # 发现候选关系
        candidates = scanner.discover_foreign_key_candidates(tables)

        # 计算匹配率并验证
        results = []
        for rel in candidates:
            match_rate = scanner.calculate_match_rate(db_name, rel)
            rel.match_rate = match_rate

            if match_rate >= settings.relationship_match_threshold:
                is_valid = analyzer.verify_relationship(rel)
                rel.verified = is_valid
                results.append(
                    RelationshipResponse(
                        source_table=rel.source_table,
                        source_column=rel.source_column,
                        target_table=rel.target_table,
                        target_column=rel.target_column,
                        relationship_type=rel.relationship_type,
                        match_rate=rel.match_rate,
                        verified=rel.verified,
                    )
                )

        return results
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发现关系失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scan", response_model=ScanProgressResponse)
async def full_scan(request: ScanRequest):
    """全量扫描数据库"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        # 扫描数据库
        tables = scanner.scan_database(request.db_name)
        if not tables:
            raise HTTPException(status_code=404, detail=f"数据库不存在：{request.db_name}")

        # 批量分析表语义
        table_semantics = analyzer.batch_analyze_tables(tables, request.db_name, request.sample_size)

        # 发现关系（如果需要）
        relationships = []
        if request.verify_relationships:
            candidates = scanner.discover_foreign_key_candidates(tables)
            for rel in candidates:
                match_rate = scanner.calculate_match_rate(request.db_name, rel)
                rel.match_rate = match_rate
                if match_rate >= settings.relationship_match_threshold:
                    is_valid = analyzer.verify_relationship(rel)
                    rel.verified = is_valid
                    relationships.append(
                        RelationshipResponse(
                            source_table=rel.source_table,
                            source_column=rel.source_column,
                            target_table=rel.target_table,
                            target_column=rel.target_column,
                            relationship_type=rel.relationship_type,
                            match_rate=rel.match_rate,
                            verified=rel.verified,
                        )
                    )

        # 返回结果
        return JSONResponse(
            content={
                "status": "completed",
                "database": request.db_name,
                "tables": [
                    {
                        "table_name": ts.table_name,
                        "chinese_name": ts.chinese_name,
                        "business_definition": ts.business_definition,
                        "data_category": ts.data_category.value,
                        "fields": [
                            {
                                "column_name": fs.column_name,
                                "data_type": fs.data_type,
                                "chinese_name": fs.chinese_name,
                                "business_definition": fs.business_definition,
                                "data_category": fs.data_category.value,
                            }
                            for fs in ts.field_semantics
                        ],
                    }
                    for ts in table_semantics
                ],
                "relationships": relationships,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"全量扫描失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 审核相关 API ====================


def _parse_field_id(field_id: str) -> tuple[str, str, str]:
    """解析 field_id (格式：db.table.column)"""
    parts = field_id.split(".")
    if len(parts) < 3:
        raise ValueError(f"无效的 field_id 格式：{field_id}，应为 db.table.column")
    db_name = parts[0]
    table_name = parts[1]
    column_name = ".".join(parts[2:])  # 支持列名中包含点
    return db_name, table_name, column_name


@app.get("/review/pending", response_model=ReviewPendingResponse)
async def get_pending_reviews(db_name: Optional[str] = Query(None, description="可选的数据库名过滤")):
    """获取待审核字段列表"""
    pending_data = chroma_store.get_pending_fields(db_name)

    pending_fields = [
        ReviewPendingItem(
            id=item["field_id"],
            db_name=item["db_name"],
            table_name=item["table_name"],
            column_name=item["column_name"],
            data_type=item.get("data_type", ""),
            chinese_name=item.get("chinese_name"),
            business_definition=item.get("business_definition"),
            value_rules=item.get("value_rules"),
            related_fields=item.get("related_fields", []),
            data_category=DataCategory(item.get("data_category", "other")) if item.get("data_category") else DataCategory.OTHER,
            created_at=datetime.fromisoformat(item["created_at"]) if item.get("created_at") else datetime.now(),
        )
        for item in pending_data
    ]

    return ReviewPendingResponse(
        total=len(pending_fields),
        pending_fields=pending_fields,
    )


@app.post("/review/submit", response_model=ReviewResultResponse)
async def submit_review(request: ReviewSubmitRequest):
    """提交审核（确认字段语义）"""
    try:
        success = chroma_store.submit_field(request.field_id, request.calibrated_by, request.modifications)

        if success:
            return ReviewResultResponse(
                success=True,
                field_id=request.field_id,
                status=ColumnType.CALIBRATED,
                message="审核通过",
            )
        else:
            return ReviewResultResponse(
                success=False,
                field_id=request.field_id,
                status=ColumnType.PENDING,
                message="字段不存在或不是待审核状态",
            )
    except Exception as e:
        return ReviewResultResponse(
            success=False,
            field_id=request.field_id,
            status=ColumnType.PENDING,
            message=str(e),
        )


@app.post("/review/reject", response_model=ReviewResultResponse)
async def reject_review(request: ReviewRejectRequest):
    """拒绝字段（标记为跳过）"""
    try:
        success = chroma_store.reject_field(request.field_id)

        if success:
            return ReviewResultResponse(
                success=True,
                field_id=request.field_id,
                status=ColumnType.SKIPPED,
                message=request.reason or "已拒绝",
            )
        else:
            return ReviewResultResponse(
                success=False,
                field_id=request.field_id,
                status=ColumnType.PENDING,
                message="字段不存在或不是待审核状态",
            )
    except Exception as e:
        return ReviewResultResponse(
            success=False,
            field_id=request.field_id,
            status=ColumnType.PENDING,
            message=str(e),
        )


@app.post("/review/modify", response_model=ReviewResultResponse)
async def modify_and_confirm(request: ReviewModifyRequest):
    """修改并确认字段语义"""
    try:
        success = chroma_store.modify_field(request.field_id, request.modifications, request.calibrated_by)

        if success:
            return ReviewResultResponse(
                success=True,
                field_id=request.field_id,
                status=ColumnType.CALIBRATED,
                message="修改并确认成功",
            )
        else:
            return ReviewResultResponse(
                success=False,
                field_id=request.field_id,
                status=ColumnType.PENDING,
                message="字段不存在或不是待审核状态",
            )
    except Exception as e:
        return ReviewResultResponse(
            success=False,
            field_id=request.field_id,
            status=ColumnType.PENDING,
            message=str(e),
        )


# ==================== 自然语言查询 API ====================


@app.post("/query", response_model=QueryResponse)
async def natural_language_query(request: QueryRequest):
    """自然语言查询数据库语义"""
    try:
        from core.query_engine import QueryEngine

        engine = QueryEngine()
        result = engine.query(question=request.question, db_name=request.db_name, top_k=request.top_k)

        return QueryResponse(
            question=result.question,
            answer=result.answer,
            relevant_fields=[
                QueryFieldResult(
                    column_name=f.get("column_name", ""),
                    table_name=f.get("table_name", ""),
                    db_name=f.get("db_name", ""),
                    data_type=f.get("data_type", ""),
                    chinese_name=f.get("chinese_name"),
                    business_definition=f.get("business_definition"),
                    value_rules=f.get("value_rules"),
                    data_category=DataCategory(f.get("data_category", "other")),
                    relevance_score=f.get("relevance_score", 0.0),
                )
                for f in result.fields
            ],
            relevant_tables=[
                QueryTableResult(
                    table_name=t.get("table_name", ""),
                    db_name=t.get("db_name", ""),
                    chinese_name=t.get("chinese_name"),
                    business_definition=t.get("business_definition"),
                    data_category=DataCategory(t.get("data_category", "fact")),
                    relevance_score=t.get("relevance_score", 0.0),
                )
                for t in result.tables
            ],
            has_error=result.has_error,
            error_message=result.error_message,
        )
    except Exception as e:
        logger.error(f"自然语言查询失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 语义缓存相关 API ====================


def _get_empty_field_cache(db_name: str, table_name: str, column_name: str, data_type: str = "") -> FieldSemanticCacheResponse:
    """返回空的字段语义缓存响应"""
    return FieldSemanticCacheResponse(
        id=f"{db_name}.{table_name}.{column_name}",
        db_name=db_name,
        table_name=table_name,
        column_name=column_name,
        data_type=data_type,
        has_semantics=False,
    )


def _get_empty_table_cache(db_name: str, table_name: str) -> TableSemanticCacheResponse:
    """返回空的表语义缓存响应"""
    return TableSemanticCacheResponse(
        id=f"{db_name}.{table_name}",
        db_name=db_name,
        table_name=table_name,
        has_semantics=False,
    )


@app.get("/databases/{db_name}/tables/{table_name}/semantic", response_model=TableSemanticCacheResponse)
async def get_table_semantic_cache(db_name: str, table_name: str):
    """获取表级语义信息（从 ChromaDB 或 Milvus）"""
    try:
        storage_type = settings.semantic_storage_type

        if storage_type == "milvus":
            from core.knowledge_base import KnowledgeBase

            kb = KnowledgeBase()
            kb.connect()

            try:
                # 查询表级语义
                filter_expr = f'db_name == "{db_name}" and table_name == "{table_name}" and column_name == ""'
                table_results = kb.vector_store.search(
                    collection_name=settings.milvus_table_collection,
                    query_vector=[0] * kb.embedding_service.dimension,
                    top_k=1,
                    filter_expr=filter_expr,
                )

                if not table_results:
                    return _get_empty_table_cache(db_name, table_name)

                table_data = table_results[0]

                # 查询字段级语义
                field_filter = f'db_name == "{db_name}" and table_name == "{table_name}"'
                field_results = kb.get_fields_by_table(db_name, table_name)

                fields = []
                for f in field_results:
                    fields.append({
                        "id": f.get("id", f"{db_name}.{table_name}.{f.get('column_name', '')}"),
                        "db_name": f.get("db_name", db_name),
                        "table_name": f.get("table_name", table_name),
                        "column_name": f.get("column_name", ""),
                        "data_type": f.get("data_type", ""),
                        "chinese_name": f.get("chinese_name"),
                        "business_definition": f.get("business_definition"),
                        "value_rules": f.get("value_rules"),
                        "related_fields": [],
                        "data_category": f.get("data_category", "other"),
                        "status": None,
                        "has_semantics": True,
                    })

                return TableSemanticCacheResponse(
                    id=table_data.get("id", f"{db_name}.{table_name}"),
                    db_name=table_data.get("db_name", db_name),
                    table_name=table_data.get("table_name", table_name),
                    chinese_name=table_data.get("chinese_name"),
                    business_definition=table_data.get("business_definition"),
                    data_category=DataCategory(table_data.get("data_category", "fact")),
                    has_semantics=True,
                    fields=fields if fields else None,
                )
            finally:
                kb.disconnect()
        else:
            # ChromaDB
            result = chroma_store.get_table_semantic(db_name, table_name)

            if not result:
                return _get_empty_table_cache(db_name, table_name)

            fields = []
            for f in result.get("fields", []):
                fields.append({
                    "id": f"{db_name}.{table_name}.{f.get('column_name', '')}",
                    "db_name": db_name,
                    "table_name": table_name,
                    "column_name": f.get("column_name", ""),
                    "data_type": f.get("data_type", ""),
                    "chinese_name": f.get("chinese_name"),
                    "business_definition": f.get("business_definition"),
                    "value_rules": f.get("value_rules"),
                    "related_fields": f.get("related_fields", []),
                    "data_category": f.get("data_category", "other"),
                    "status": f.get("status"),
                    "has_semantics": True,
                })

            return TableSemanticCacheResponse(
                id=f"{db_name}.{table_name}",
                db_name=db_name,
                table_name=table_name,
                chinese_name=result.get("chinese_name"),
                business_definition=result.get("business_definition"),
                data_category=DataCategory(result.get("data_category", "fact")),
                has_semantics=True,
                fields=fields if fields else None,
            )
    except Exception as e:
        logger.error(f"获取表语义缓存失败：{e}")
        return _get_empty_table_cache(db_name, table_name)


@app.get("/databases/{db_name}/tables/{table_name}/field/{column_name}/semantic", response_model=FieldSemanticCacheResponse)
async def get_field_semantic_cache(db_name: str, table_name: str, column_name: str):
    """获取字段级语义信息（从 ChromaDB 或 Milvus）"""
    try:
        storage_type = settings.semantic_storage_type

        if storage_type == "milvus":
            from core.knowledge_base import KnowledgeBase

            kb = KnowledgeBase()
            kb.connect()

            try:
                # 查询字段级语义
                filter_expr = f'db_name == "{db_name}" and table_name == "{table_name}" and column_name == "{column_name}"'
                results = kb.vector_store.search(
                    collection_name=settings.milvus_field_collection,
                    query_vector=[0] * kb.embedding_service.dimension,
                    top_k=1,
                    filter_expr=filter_expr,
                )

                if not results:
                    return _get_empty_field_cache(db_name, table_name, column_name)

                field_data = results[0]

                return FieldSemanticCacheResponse(
                    id=field_data.get("id", f"{db_name}.{table_name}.{column_name}"),
                    db_name=field_data.get("db_name", db_name),
                    table_name=field_data.get("table_name", table_name),
                    column_name=field_data.get("column_name", column_name),
                    data_type=field_data.get("data_type", ""),
                    chinese_name=field_data.get("chinese_name"),
                    business_definition=field_data.get("business_definition"),
                    value_rules=field_data.get("value_rules"),
                    related_fields=[],
                    data_category=DataCategory(field_data.get("data_category", "other")),
                    status=None,
                    has_semantics=True,
                )
            finally:
                kb.disconnect()
        else:
            # ChromaDB: 先获取整个表的语义，然后筛选指定字段
            result = chroma_store.get_table_semantic(db_name, table_name)

            if not result:
                # 需要先获取字段的数据类型
                scanner = get_scanner()
                tables = scanner.scan_database(db_name)
                data_type = ""
                for table in tables:
                    if table.table_name == table_name:
                        for col in table.columns:
                            if col.column_name == column_name:
                                data_type = col.data_type
                                break
                        break
                return _get_empty_field_cache(db_name, table_name, column_name, data_type)

            # 查找指定字段
            for field in result.get("fields", []):
                if field.get("column_name") == column_name:
                    status_val = field.get("status")
                    return FieldSemanticCacheResponse(
                        id=f"{db_name}.{table_name}.{column_name}",
                        db_name=db_name,
                        table_name=table_name,
                        column_name=field.get("column_name", column_name),
                        data_type=field.get("data_type", ""),
                        chinese_name=field.get("chinese_name"),
                        business_definition=field.get("business_definition"),
                        value_rules=field.get("value_rules"),
                        related_fields=field.get("related_fields", []),
                        data_category=DataCategory(field.get("data_category", "other")),
                        status=ColumnType(status_val.lower()) if status_val else None,
                        has_semantics=True,
                    )

            # 字段不存在
            return _get_empty_field_cache(db_name, table_name, column_name)
    except Exception as e:
        logger.error(f"获取字段语义缓存失败：{e}")
        return _get_empty_field_cache(db_name, table_name, column_name)


@app.put("/tables/semantic", response_model=TableSemanticResponse)
async def update_table_semantic(request: UpdateTableSemanticRequest):
    """更新表级语义信息"""
    try:
        storage_type = settings.semantic_storage_type

        if storage_type == "milvus":
            # Milvus 暂不支持直接更新，返回错误
            logger.warning("Milvus 暂不支持直接更新表语义")
            raise HTTPException(status_code=501, detail="Milvus 暂不支持直接更新表语义")
        else:
            # ChromaDB: 更新表中所有字段的表级元数据
            result = chroma_store.get_table_semantic(request.db_name, request.table_name)

            if not result:
                raise HTTPException(status_code=404, detail=f"表不存在：{request.db_name}.{request.table_name}")

            # 构建更新内容
            updates: Dict[str, Any] = {}
            if request.chinese_name is not None:
                updates["table_chinese_name"] = request.chinese_name
            if request.business_definition is not None:
                updates["table_business_definition"] = request.business_definition
            if request.data_category is not None:
                updates["table_data_category"] = request.data_category.value

            # 获取所有字段 ID 并更新
            ids = [f"{request.db_name}.{request.table_name}.{f['column_name']}" for f in result.get("fields", [])]

            if ids and updates:
                chroma_store.collection.update(ids=ids, metadatas=[updates] * len(ids))

            # 返回更新后的结果
            updated_result = chroma_store.get_table_semantic(request.db_name, request.table_name)

            return TableSemanticResponse(
                table_name=updated_result["table_name"],
                db_name=updated_result["db_name"],
                chinese_name=updated_result.get("chinese_name"),
                business_definition=updated_result.get("business_definition"),
                data_category=DataCategory(updated_result.get("data_category", "fact")),
                fields=[
                    FieldSemanticResponse(
                        id=f"{request.db_name}.{request.table_name}.{f['column_name']}",
                        db_name=request.db_name,
                        table_name=request.table_name,
                        column_name=f["column_name"],
                        data_type=f["data_type"],
                        chinese_name=f.get("chinese_name"),
                        business_definition=f.get("business_definition"),
                        value_rules=f.get("value_rules"),
                        related_fields=f.get("related_fields", []),
                        data_category=DataCategory(f.get("data_category", "other")),
                        status=ColumnType(f.get("status", "AUTO")),
                    )
                    for f in updated_result.get("fields", [])
                ],
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新表语义失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/fields/semantic", response_model=FieldSemanticResponse)
async def update_field_semantic(request: UpdateFieldSemanticRequest):
    """更新字段级语义信息"""
    try:
        storage_type = settings.semantic_storage_type

        if storage_type == "milvus":
            # Milvus 暂不支持直接更新，返回错误
            logger.warning("Milvus 暂不支持直接更新字段语义")
            raise HTTPException(status_code=501, detail="Milvus 暂不支持直接更新字段语义")
        else:
            # ChromaDB: 更新字段元数据
            updates: Dict[str, Any] = {}
            if request.chinese_name is not None:
                updates["chinese_name"] = request.chinese_name
            if request.business_definition is not None:
                updates["business_definition"] = request.business_definition
            if request.value_rules is not None:
                updates["value_rules"] = request.value_rules
            if request.data_category is not None:
                updates["data_category"] = request.data_category.value

            if updates:
                chroma_store.collection.update(ids=[request.field_id], metadatas=[updates])

            # 返回更新后的结果
            parts = request.field_id.split(".")
            if len(parts) >= 3:
                db_name = parts[0]
                table_name = parts[1]
                column_name = ".".join(parts[2:])

                result = chroma_store.get_table_semantic(db_name, table_name)

                if result:
                    for field in result.get("fields", []):
                        if field.get("column_name") == column_name:
                            return FieldSemanticResponse(
                                id=request.field_id,
                                db_name=db_name,
                                table_name=table_name,
                                column_name=column_name,
                                data_type=field.get("data_type", ""),
                                chinese_name=field.get("chinese_name"),
                                business_definition=field.get("business_definition"),
                                value_rules=field.get("value_rules"),
                                related_fields=field.get("related_fields", []),
                                data_category=DataCategory(field.get("data_category", "other")),
                                status=ColumnType(field.get("status", "AUTO")),
                            )

            raise HTTPException(status_code=404, detail=f"字段不存在：{request.field_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新字段语义失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))
