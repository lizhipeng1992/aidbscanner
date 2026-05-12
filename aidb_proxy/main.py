"""AI Database Proxy - FastAPI Application"""
import logging
from typing import List, Optional, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from config.settings import settings
from core.semantic_analyzer import SemanticAnalyzer
from core.models import FieldSemantic, ColumnType, DataCategory
from datetime import datetime
from core.chroma_store import ChromaStore
from aidb_proxy.schemas import (
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
    ReviewPendingResponse,
    ReviewPendingItem,
    ReviewSubmitRequest,
    ReviewRejectRequest,
    ReviewModifyRequest,
    ReviewResultResponse,
    QueryRequest,
    QueryResponse,
    QueryFieldResult,
    QueryTableResult,
    FieldSemanticCacheResponse,
    TableSemanticCacheResponse,
)

logger = logging.getLogger(__name__)

chroma_store = ChromaStore(settings.semantic_storage_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    logger.info("AI Database Proxy starting")
    yield
    logger.info("AI Database Proxy stopping")


app = FastAPI(
    title="AI Database Proxy",
    description="AI Database Semantic Layer API Service",
    version="1.0.0",
    lifespan=lifespan,
)


def get_scanner():
    db_type = settings.db_type
    if db_type == "gbase":
        from core.gbase_scanner import GBaseScanner
        return GBaseScanner()
    elif db_type == "sqlserver":
        from core.sqlserver_scanner import SQLServerScanner
        return SQLServerScanner()
    else:
        from core.scanner import MySQLScanner
        return MySQLScanner()


def get_analyzer(scanner = None) -> SemanticAnalyzer:
    if scanner is None:
        scanner = get_scanner()
    return SemanticAnalyzer(scanner)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check"""
    from core.llm_client import LLMProvider, create_llm_client, ChatMessage

    db_status = "unknown"
    llm_status = "unknown"

    try:
        scanner = get_scanner()
        scanner.list_databases()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

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
            client.models.list()
            llm_status = "connected"
    except Exception as e:
        llm_status = f"error: {str(e)}"

    return HealthResponse(
        status="healthy",
        database=db_status,
        llm=llm_status,
        llm_provider=settings.llm_provider.value,
    )


@app.get("/databases", response_model=DatabaseListResponse)
async def list_databases():
    """List all databases"""
    try:
        scanner = get_scanner()
        databases = scanner.list_databases()
        system_dbs = {"information_schema", "mysql", "performance_schema", "sys"}
        databases = [db for db in databases if db not in system_dbs]
        return DatabaseListResponse(databases=databases)
    except Exception as e:
        logger.error(f"Failed to get database list: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/databases/{db_name}/tables", response_model=TableListResponse)
async def list_tables(db_name: str):
    """List all tables in a specified database"""
    try:
        scanner = get_scanner()
        tables = scanner.scan_database(db_name)

        if not tables:
            raise HTTPException(status_code=404, detail=f"Database does not exist: {db_name}")

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
        logger.error(f"Failed to get table list: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/fields/analyze", response_model=FieldSemanticResponse)
async def analyze_field(request: FieldSemanticRequest):
    """Analyze semantics of a single field"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        tables = scanner.scan_database(request.db_name)
        if not tables:
            raise HTTPException(status_code=404, detail=f"Database does not exist: {request.db_name}")

        target_table = next((t for t in tables if t.table_name == request.table_name), None)
        if not target_table:
            raise HTTPException(status_code=404, detail=f"Table does not exist: {request.table_name}")

        target_column = next((c for c in target_table.columns if c.column_name == request.column_name), None)
        if not target_column:
            raise HTTPException(status_code=404, detail=f"Field does not exist: {request.column_name}")

        sample_values = scanner.get_sample_data(
            request.db_name, request.table_name, request.column_name
        )

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
        logger.error(f"Failed to analyze field semantics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tables/analyze", response_model=TableSemanticResponse)
async def analyze_table(request: TableSemanticRequest):
    """Analyze the semantics of an entire table"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        tables = scanner.scan_database(request.db_name)
        if not tables:
            raise HTTPException(status_code=404, detail=f"Database does not exist: {request.db_name}")

        target_table = next((t for t in tables if t.table_name == request.table_name), None)
        if not target_table:
            raise HTTPException(status_code=404, detail=f"Table does not exist: {request.table_name}")

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
        logger.error(f"Failed to analyze table semantics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/relationships/verify", response_model=RelationshipResponse)
async def verify_relationship(request: RelationshipVerifyRequest):
    """Verify relationships between tables"""
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

        match_rate = scanner.calculate_match_rate(request.db_name, rel)
        rel.match_rate = match_rate

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
        logger.error(f"Failed to verify relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/discover/relationships", response_model=List[RelationshipResponse])
async def discover_relationships(db_name: str = Query(..., description="Database name")):
    """Discover potential foreign key relationships"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        tables = scanner.scan_database(db_name)
        if not tables:
            raise HTTPException(status_code=404, detail=f"Database does not exist: {db_name}")

        candidates = scanner.discover_foreign_key_candidates(tables)

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
        logger.error(f"Failed to discover relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scan", response_model=ScanProgressResponse)
async def full_scan(request: ScanRequest):
    """Full scan of database"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        tables = scanner.scan_database(request.db_name)
        if not tables:
            raise HTTPException(status_code=404, detail=f"Database does not exist: {request.db_name}")

        table_semantics = analyzer.batch_analyze_tables(tables, request.db_name, request.sample_size)

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
        logger.error(f"Full scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _parse_field_id(field_id: str) -> tuple[str, str, str]:
    """Parse field_id (format: db.table.column)"""
    parts = field_id.split(".")
    if len(parts) < 3:
        raise ValueError(f"Invalid field_id format: {field_id}, expected db.table.column")
    db_name = parts[0]
    table_name = parts[1]
    column_name = ".".join(parts[2:])
    return db_name, table_name, column_name


@app.get("/review/pending", response_model=ReviewPendingResponse)
async def get_pending_reviews(db_name: Optional[str] = Query(None, description="Optional database name filter")):
    """Get pending field review list"""
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
    """Submit review (confirm field semantics)"""
    try:
        success = chroma_store.submit_field(request.field_id, request.calibrated_by, request.modifications)

        if success:
            return ReviewResultResponse(
                success=True,
                field_id=request.field_id,
                status=ColumnType.CALIBRATED,
                message="Review passed",
            )
        else:
            return ReviewResultResponse(
                success=False,
                field_id=request.field_id,
                status=ColumnType.PENDING,
                message="Field does not exist or is not in pending review status",
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
    """Reject field (mark as skipped)"""
    try:
        success = chroma_store.reject_field(request.field_id)

        if success:
            return ReviewResultResponse(
                success=True,
                field_id=request.field_id,
                status=ColumnType.SKIPPED,
                message=request.reason or "Rejected",
            )
        else:
            return ReviewResultResponse(
                success=False,
                field_id=request.field_id,
                status=ColumnType.PENDING,
                message="Field does not exist or is not in pending review status",
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
    """Modify and confirm field semantics"""
    try:
        success = chroma_store.modify_field(request.field_id, request.modifications, request.calibrated_by)

        if success:
            return ReviewResultResponse(
                success=True,
                field_id=request.field_id,
                status=ColumnType.CALIBRATED,
                message="Modified and confirmed successfully",
            )
        else:
            return ReviewResultResponse(
                success=False,
                field_id=request.field_id,
                status=ColumnType.PENDING,
                message="Field does not exist or is not in pending review status",
            )
    except Exception as e:
        return ReviewResultResponse(
            success=False,
            field_id=request.field_id,
            status=ColumnType.PENDING,
            message=str(e),
        )


# ==================== Natural Language Query API ====================


@app.post("/query", response_model=QueryResponse)
async def natural_language_query(request: QueryRequest):
    """Query database semantics with natural language"""
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
        logger.error(f"Natural language query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Semantic Cache API ====================


def _get_empty_field_cache(db_name: str, table_name: str, column_name: str, data_type: str = "") -> FieldSemanticCacheResponse:
    """Return empty field semantic cache response"""
    return FieldSemanticCacheResponse(
        id=f"{db_name}.{table_name}.{column_name}",
        db_name=db_name,
        table_name=table_name,
        column_name=column_name,
        data_type=data_type,
        has_semantics=False,
    )


def _get_empty_table_cache(db_name: str, table_name: str) -> TableSemanticCacheResponse:
    """Return empty table semantic cache response"""
    return TableSemanticCacheResponse(
        id=f"{db_name}.{table_name}",
        db_name=db_name,
        table_name=table_name,
        has_semantics=False,
    )


@app.get("/databases/{db_name}/tables/{table_name}/semantic", response_model=TableSemanticCacheResponse)
async def get_table_semantic_cache(db_name: str, table_name: str):
    """Get table-level semantic info (from ChromaDB)"""
    try:
        result = chroma_store.get_table_semantic(db_name, table_name)

        if not result:
            return _get_empty_table_cache(db_name, table_name)

        fields = []
        for f in result.get("fields", []):
            fields.append(
                FieldSemanticCacheResponse(
                    id=f"{db_name}.{table_name}.{f.get('column_name', '')}",
                    db_name=db_name,
                    table_name=table_name,
                    column_name=f.get("column_name", ""),
                    data_type=f.get("data_type", ""),
                    chinese_name=f.get("chinese_name"),
                    business_definition=f.get("business_definition"),
                    value_rules=f.get("value_rules"),
                    related_fields=f.get("related_fields", []),
                    data_category=DataCategory(f.get("data_category", "other")) if f.get("data_category") else None,
                    status=ColumnType(f.get("status")) if f.get("status") else None,
                    has_semantics=True,
                )
            )

        return TableSemanticCacheResponse(
            id=f"{db_name}.{table_name}",
            db_name=db_name,
            table_name=table_name,
            chinese_name=result.get("chinese_name"),
            business_definition=result.get("business_definition"),
            data_category=DataCategory(result.get("data_category", "fact")) if result.get("data_category") else None,
            has_semantics=True,
            fields=fields if fields else None,
        )
    except Exception as e:
        logger.error(f"Failed to get table semantic cache: {e}")
        return _get_empty_table_cache(db_name, table_name)


@app.get("/databases/{db_name}/tables/{table_name}/field/{column_name}/semantic", response_model=FieldSemanticCacheResponse)
async def get_field_semantic_cache(db_name: str, table_name: str, column_name: str):
    """Get field-level semantic info (from ChromaDB)"""
    try:
        result = chroma_store.get_table_semantic(db_name, table_name)

        if not result:
            # Need to get field data type
            scanner = get_scanner()
            tables = scanner.scan_database(db_name)
            data_type = ""
            for table in tables:
                if table.table_name == table_name:
                    for col in table.columns:
                        if col.column_name == column_name:
                            data_type = col.data_type
                            break
                    if data_type:
                        break
            return _get_empty_field_cache(db_name, table_name, column_name, data_type)

        for f in result.get("fields", []):
            if f.get("column_name") == column_name:
                return FieldSemanticCacheResponse(
                    id=f"{db_name}.{table_name}.{column_name}",
                    db_name=db_name,
                    table_name=table_name,
                    column_name=column_name,
                    data_type=f.get("data_type", ""),
                    chinese_name=f.get("chinese_name"),
                    business_definition=f.get("business_definition"),
                    value_rules=f.get("value_rules"),
                    related_fields=f.get("related_fields", []),
                    data_category=DataCategory(f.get("data_category", "other")) if f.get("data_category") else None,
                    status=ColumnType(f.get("status")) if f.get("status") else None,
                    has_semantics=True,
                )

        # Field not in semantic cache
        scanner = get_scanner()
        tables = scanner.scan_database(db_name)
        data_type = ""
        for table in tables:
            if table.table_name == table_name:
                for col in table.columns:
                    if col.column_name == column_name:
                        data_type = col.data_type
                        break
                if data_type:
                    break
        return _get_empty_field_cache(db_name, table_name, column_name, data_type)
    except Exception as e:
        logger.error(f"Failed to get field semantic cache: {e}")
        return _get_empty_field_cache(db_name, table_name, column_name)
