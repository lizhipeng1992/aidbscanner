"""API request/response model definitions"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

from core.models import ColumnType, DataCategory


class DatabaseListResponse(BaseModel):
    """Database list response"""
    databases: List[str]


class TableMetadataResponse(BaseModel):
    """Table metadata response"""
    table_name: str
    table_comment: Optional[str] = None
    engine: Optional[str] = None
    columns: List[Dict[str, Any]]


class TableListResponse(BaseModel):
    """Table list response"""
    database: str
    tables: List[TableMetadataResponse]


class FieldSemanticRequest(BaseModel):
    """Field semantic analysis request"""
    db_name: str
    table_name: str
    column_name: str


class FieldSemanticResponse(BaseModel):
    """Field semantic response"""
    id: str
    db_name: str
    table_name: str
    column_name: str
    data_type: str
    chinese_name: Optional[str] = None
    business_definition: Optional[str] = None
    value_rules: Optional[str] = None
    related_fields: List[str] = []
    data_category: DataCategory = DataCategory.OTHER
    status: ColumnType = ColumnType.PENDING


class TableSemanticRequest(BaseModel):
    """Table semantic analysis request"""
    db_name: str
    table_name: str
    sample_size: int = Field(default=5, ge=1, le=20)


class TableSemanticResponse(BaseModel):
    """Table semantic response"""
    table_name: str
    db_name: str
    chinese_name: Optional[str] = None
    business_definition: Optional[str] = None
    data_category: DataCategory = DataCategory.FACT
    fields: List[FieldSemanticResponse]


class RelationshipResponse(BaseModel):
    """Relationship response"""
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str
    match_rate: float
    verified: bool


class RelationshipVerifyRequest(BaseModel):
    """Relationship verification request"""
    db_name: str
    source_table: str
    source_column: str
    target_table: str
    target_column: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    database: str
    llm: str  # LLM service status (ollama or openai)
    llm_provider: Optional[str] = None  # Currently used LLM provider
    timestamp: datetime = Field(default_factory=datetime.now)


class ScanRequest(BaseModel):
    """Full scan request"""
    db_name: str
    sample_size: int = Field(default=5, ge=1, le=20)
    verify_relationships: bool = True


class ScanProgressResponse(BaseModel):
    """Scan progress response"""
    status: str
    current: int
    total: int
    current_table: Optional[str] = None
    message: Optional[str] = None


# ==================== Review Models ====================

class ReviewPendingItem(BaseModel):
    """Pending review field item"""
    id: str
    db_name: str
    table_name: str
    column_name: str
    data_type: str
    chinese_name: Optional[str] = None
    business_definition: Optional[str] = None
    value_rules: Optional[str] = None
    related_fields: List[str] = []
    data_category: DataCategory = DataCategory.OTHER
    created_at: datetime


class ReviewPendingResponse(BaseModel):
    """Pending review list response"""
    total: int
    pending_fields: List[ReviewPendingItem]


class ReviewSubmitRequest(BaseModel):
    """Submit review request"""
    field_id: str  # db.table.column
    calibrated_by: str
    modifications: Optional[Dict[str, Any]] = None


class ReviewRejectRequest(BaseModel):
    """Reject review request"""
    field_id: str  # db.table.column
    reason: Optional[str] = None


class ReviewModifyRequest(BaseModel):
    """Modify and confirm request"""
    field_id: str  # db.table.column
    calibrated_by: str
    modifications: Dict[str, Any]


class ReviewResultResponse(BaseModel):
    """Review result response"""
    success: bool
    field_id: str
    status: ColumnType
    message: Optional[str] = None


# ==================== Query Models ====================

class QueryRequest(BaseModel):
    """Natural language query request"""
    question: str
    db_name: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=50)


class QueryFieldResult(BaseModel):
    """Field info in query result"""
    column_name: str
    table_name: str
    db_name: str
    data_type: str = ""
    chinese_name: Optional[str] = None
    business_definition: Optional[str] = None
    value_rules: Optional[str] = None
    data_category: DataCategory = DataCategory.OTHER
    relevance_score: float = 0.0


class QueryTableResult(BaseModel):
    """Table info in query result"""
    table_name: str
    db_name: str
    chinese_name: Optional[str] = None
    business_definition: Optional[str] = None
    data_category: DataCategory = DataCategory.FACT
    relevance_score: float = 0.0


class QueryResponse(BaseModel):
    """Natural language query response"""
    question: str
    answer: str
    relevant_fields: List[QueryFieldResult] = []
    relevant_tables: List[QueryTableResult] = []
    has_error: bool = False
    error_message: Optional[str] = None


# ==================== Semantic Cache Models ====================

class FieldSemanticCacheResponse(BaseModel):
    """Field semantic cache response"""
    id: str
    db_name: str
    table_name: str
    column_name: str
    data_type: str = ""
    chinese_name: Optional[str] = None
    business_definition: Optional[str] = None
    value_rules: Optional[str] = None
    related_fields: List[str] = []
    data_category: Optional[DataCategory] = None
    status: Optional[ColumnType] = None
    has_semantics: bool = False


class TableSemanticCacheResponse(BaseModel):
    """Table semantic cache response"""
    id: str
    db_name: str
    table_name: str
    chinese_name: Optional[str] = None
    business_definition: Optional[str] = None
    data_category: Optional[DataCategory] = None
    has_semantics: bool = False
    fields: Optional[List[FieldSemanticCacheResponse]] = None
