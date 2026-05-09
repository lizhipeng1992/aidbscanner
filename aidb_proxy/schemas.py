"""API 请求/响应模型定义"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

from core.models import ColumnType, DataCategory


class DatabaseListResponse(BaseModel):
    """数据库列表响应"""
    databases: List[str]


class TableMetadataResponse(BaseModel):
    """表元数据响应"""
    table_name: str
    table_comment: Optional[str] = None
    engine: str = "InnoDB"
    columns: List[Dict[str, Any]]


class TableListResponse(BaseModel):
    """表列表响应"""
    database: str
    tables: List[TableMetadataResponse]


class FieldSemanticRequest(BaseModel):
    """字段语义分析请求"""
    db_name: str
    table_name: str
    column_name: str


class FieldSemanticResponse(BaseModel):
    """字段语义响应"""
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
    """表语义分析请求"""
    db_name: str
    table_name: str
    sample_size: int = Field(default=5, ge=1, le=20)


class TableSemanticResponse(BaseModel):
    """表语义响应"""
    table_name: str
    db_name: str
    chinese_name: Optional[str] = None
    business_definition: Optional[str] = None
    data_category: DataCategory = DataCategory.FACT
    fields: List[FieldSemanticResponse]


class RelationshipResponse(BaseModel):
    """关系响应"""
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str
    match_rate: float
    verified: bool


class RelationshipVerifyRequest(BaseModel):
    """关系验证请求"""
    db_name: str
    source_table: str
    source_column: str
    target_table: str
    target_column: str


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    mysql: str
    llm: str  # LLM 服务状态（ollama 或 openai）
    llm_provider: Optional[str] = None  # 当前使用的 LLM 提供商
    timestamp: datetime = Field(default_factory=datetime.now)


class ScanRequest(BaseModel):
    """全量扫描请求"""
    db_name: str
    sample_size: int = Field(default=5, ge=1, le=20)
    verify_relationships: bool = True


class ScanProgressResponse(BaseModel):
    """扫描进度响应"""
    status: str
    current: int
    total: int
    current_table: Optional[str] = None
    message: Optional[str] = None


# ==================== 审核相关模型 ====================

class ReviewPendingItem(BaseModel):
    """待审核字段项"""
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
    """待审核列表响应"""
    total: int
    pending_fields: List[ReviewPendingItem]


class ReviewSubmitRequest(BaseModel):
    """提交审核请求"""
    field_id: str  # db.table.column
    calibrated_by: str
    modifications: Optional[Dict[str, Any]] = None


class ReviewRejectRequest(BaseModel):
    """拒绝审核请求"""
    field_id: str  # db.table.column
    reason: Optional[str] = None


class ReviewModifyRequest(BaseModel):
    """修改并确认请求"""
    field_id: str  # db.table.column
    calibrated_by: str
    modifications: Dict[str, Any]


class ReviewResultResponse(BaseModel):
    """审核结果响应"""
    success: bool
    field_id: str
    status: ColumnType
    message: Optional[str] = None


# ==================== 查询相关模型 ====================

class QueryRequest(BaseModel):
    """自然语言查询请求"""
    question: str
    db_name: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=50)


class QueryFieldResult(BaseModel):
    """查询结果中的字段信息"""
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
    """查询结果中的表信息"""
    table_name: str
    db_name: str
    chinese_name: Optional[str] = None
    business_definition: Optional[str] = None
    data_category: DataCategory = DataCategory.FACT
    relevance_score: float = 0.0


class QueryResponse(BaseModel):
    """自然语言查询响应"""
    question: str
    answer: str
    relevant_fields: List[QueryFieldResult] = []
    relevant_tables: List[QueryTableResult] = []
    has_error: bool = False
    error_message: Optional[str] = None


# ==================== 语义缓存相关模型 ====================

class FieldSemanticCacheResponse(BaseModel):
    """字段语义缓存响应"""
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
    """表语义缓存响应"""
    id: str
    db_name: str
    table_name: str
    chinese_name: Optional[str] = None
    business_definition: Optional[str] = None
    data_category: Optional[DataCategory] = None
    has_semantics: bool = False
    fields: Optional[List[FieldSemanticCacheResponse]] = None
