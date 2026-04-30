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
