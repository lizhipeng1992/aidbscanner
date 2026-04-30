"""数据模型定义"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ColumnType(str, Enum):
    """字段状态枚举"""
    PENDING = "pending"  # 待审核（LLM 识别后等待人工确认）
    CALIBRATED = "calibrated"  # 已校准（人工审核确认）
    AUTO = "auto"  # 自动（自动模式下 LLM 直接保存）
    SKIPPED = "skipped"  # 已跳过


class DataCategory(str, Enum):
    """数据分类枚举"""
    DIMENSION = "dimension"  # 维度
    METRIC = "metric"  # 指标
    FACT = "fact"  # 事实
    OTHER = "other"  # 其他


class ColumnMetadata(BaseModel):
    """MySQL 字段元数据"""
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
    """MySQL 表元数据"""
    table_name: str
    table_comment: Optional[str] = None
    engine: str = "InnoDB"
    columns: List[ColumnMetadata] = []


class FieldSemantic(BaseModel):
    """字段语义信息"""
    id: str  # 唯一标识：db_name.table_name.column_name
    db_name: str
    table_name: str
    column_name: str
    data_type: str

    # AI 解析的语义信息
    chinese_name: Optional[str] = None  # 中文业务名称
    business_definition: Optional[str] = None  # 业务定义
    value_rules: Optional[str] = None  # 取值范围和规则
    related_fields: List[str] = []  # 关联字段
    data_category: DataCategory = DataCategory.OTHER  # 数据分类

    # 状态
    status: ColumnType = ColumnType.PENDING
    calibrated_by: Optional[str] = None  # 校准人
    calibrated_at: Optional[datetime] = None  # 校准时间

    # 元数据
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()


class TableSemantic(BaseModel):
    """表语义信息"""
    table_name: str
    db_name: str
    chinese_name: Optional[str] = None  # 表中文名称
    business_definition: Optional[str] = None  # 表业务定义
    data_category: DataCategory = DataCategory.FACT
    field_semantics: List[FieldSemantic] = []


class RelationshipDiscoveryMethod(str, Enum):
    """关系发现方法枚举"""
    NAMING_PATTERN = "naming_pattern"  # 命名规则匹配
    VALUE_DISTRIBUTION = "value_distribution"  # 值分布分析
    DATA_TYPE = "data_type"  # 数据类型推断


class Relationship(BaseModel):
    """表间关系"""
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str  # one-to-many, many-to-one, etc.
    match_rate: float = 0.0  # 值匹配率 (0-1)
    confidence_score: float = 0.0  # 综合置信度评分 (0-1)
    verified: bool = False  # 是否经 LLM 验证
    discovery_methods: List[RelationshipDiscoveryMethod] = []  # 发现方法
    data_type_match: bool = True  # 数据类型是否匹配
    value_overlap_rate: float = 0.0  # 值重叠率 (用于值分布分析)


class RAGContext(BaseModel):
    """RAG 检索上下文"""
    query: str
    relevant_fields: List[FieldSemantic] = []
    relevant_tables: List[TableSemantic] = []
    relationships: List[Relationship] = []

    def to_prompt(self) -> str:
        """转换为 LLM 可用的提示词格式"""
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
