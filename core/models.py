"""Data model definitions"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ColumnType(str, Enum):
    """Column type enumeration"""
    PENDING = "pending"  # Pending review (waiting for manual confirmation after LLM recognition)
    CALIBRATED = "calibrated"  # Calibrated (manually reviewed and confirmed)
    AUTO = "auto"  # Auto (LLM saves directly in auto mode)
    SKIPPED = "skipped"  # Skipped


class DataCategory(str, Enum):
    """Data category enumeration"""
    DIMENSION = "dimension"  # Dimension
    METRIC = "metric"  # Metric
    FACT = "fact"  # Fact
    OTHER = "other"  # Other


class ColumnMetadata(BaseModel):
    """MySQL column metadata"""
    column_name: str
    table_name: str
    data_type: str
    character_maximum_length: Optional[int] = None
    is_nullable: str  # "YES" or "NO"
    column_default: Optional[str] = None
    column_comment: Optional[str] = None
    is_primary_key: bool = False
    is_auto_increment: bool = False
    ordinal_position: int = 0


class TableMetadata(BaseModel):
    """MySQL table metadata"""
    table_name: str
    table_comment: Optional[str] = None
    engine: str = "InnoDB"
    columns: List[ColumnMetadata] = []


class FieldSemantic(BaseModel):
    """Field semantic information"""
    id: str  # Unique identifier: db_name.table_name.column_name
    db_name: str
    table_name: str
    column_name: str
    data_type: str

    # AI-parsed semantic information
    chinese_name: Optional[str] = None  # Chinese business name
    business_definition: Optional[str] = None  # Business definition
    value_rules: Optional[str] = None  # Value range and rules
    related_fields: List[str] = []  # Related fields
    data_category: DataCategory = DataCategory.OTHER  # Data category

    # Status
    status: ColumnType = ColumnType.PENDING
    calibrated_by: Optional[str] = None  # Calibrator
    calibrated_at: Optional[datetime] = None  # Calibration time

    # Metadata
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return self.model_dump()


class TableSemantic(BaseModel):
    """Table semantic information"""
    table_name: str
    db_name: str
    chinese_name: Optional[str] = None  # Table Chinese name
    business_definition: Optional[str] = None  # Table business definition
    data_category: DataCategory = DataCategory.FACT
    field_semantics: List[FieldSemantic] = []


class RelationshipDiscoveryMethod(str, Enum):
    """Relationship discovery method enumeration"""
    NAMING_PATTERN = "naming_pattern"  # Naming pattern matching
    VALUE_DISTRIBUTION = "value_distribution"  # Value distribution analysis
    DATA_TYPE = "data_type"  # Data type inference


class Relationship(BaseModel):
    """Relationship between tables"""
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str  # one-to-many, many-to-one, etc.
    match_rate: float = 0.0  # Value match rate (0-1)
    confidence_score: float = 0.0  # Comprehensive confidence score (0-1)
    verified: bool = False  # Whether verified by LLM
    discovery_methods: List[RelationshipDiscoveryMethod] = []  # Discovery methods
    data_type_match: bool = True  # Whether data types match
    value_overlap_rate: float = 0.0  # Value overlap rate (for value distribution analysis)


class RAGContext(BaseModel):
    """RAG retrieval context"""
    query: str
    relevant_fields: List[FieldSemantic] = []
    relevant_tables: List[TableSemantic] = []
    relationships: List[Relationship] = []

    def to_prompt(self) -> str:
        """Convert to LLM-readable prompt format"""
        parts = ["数据库 Schema 信息：\n\n"]

        if self.relevant_tables:
            parts.append("## 相关表\n")
            for table in self.relevant_tables:
                parts.append(f"### {table.table_name} ({table.chinese_name or ''})\n")
                if table.business_definition:
                    parts.append(f"说明：{table.business_definition}\n")
                parts.append("字段：\n")
                for field in table.field_semantics:
                    parts.append(
                        f"  - {field.column_name} ({field.chinese_name or ''}): "
                        f"{field.business_definition or '无说明'}\n"
                    )
                parts.append("\n")

        if self.relationships:
            parts.append("## 表关系\n")
            for rel in self.relationships:
                parts.append(
                    f"- {rel.source_table}.{rel.source_column} -> "
                    f"{rel.target_table}.{rel.target_column} ({rel.relationship_type})\n"
                )

        return "".join(parts)
