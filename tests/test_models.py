"""Data model unit tests"""
import pytest
from datetime import datetime
from uuid import UUID

from core.models import (
    ColumnMetadata,
    TableMetadata,
    FieldSemantic,
    TableSemantic,
    Relationship,
    RAGContext,
    ColumnType,
    DataCategory,
)


class TestColumnMetadata:
    """ColumnMetadata tests"""

    def test_create_column_metadata(self):
        """Test creating column metadata"""
        col = ColumnMetadata(
            column_name="user_id",
            table_name="users",
            data_type="bigint",
            ordinal_position=1,
            is_nullable="NO",
            column_default=None,
            column_comment="用户 ID",
        )
        assert col.column_name == "user_id"
        assert col.table_name == "users"
        assert col.data_type == "bigint"
        assert col.ordinal_position == 1
        assert col.is_nullable == "NO"

    def test_primary_key_property(self):
        """Test primary key property judgment"""
        col = ColumnMetadata(
            column_name="id",
            table_name="users",
            data_type="bigint",
            ordinal_position=1,
            is_nullable="NO",
            column_default=None,
            column_comment=None,
        )
        assert col.is_primary_key is False

    def test_id_suffix_property(self):
        """Test _id suffix judgment"""
        col1 = ColumnMetadata(
            column_name="user_id",
            table_name="orders",
            data_type="bigint",
            ordinal_position=1,
            is_nullable="NO",
            column_default=None,
            column_comment=None,
        )
        col2 = ColumnMetadata(
            column_name="name",
            table_name="users",
            data_type="varchar",
            ordinal_position=2,
            is_nullable="YES",
            column_default=None,
            column_comment=None,
        )
        assert col1.column_name.endswith("_id") is True
        assert col2.column_name.endswith("_id") is False


class TestTableMetadata:
    """TableMetadata tests"""

    def test_create_table_metadata(self):
        """Test creating table metadata"""
        col = ColumnMetadata(
            column_name="id",
            table_name="users",
            data_type="bigint",
            ordinal_position=1,
            is_nullable="NO",
            column_default=None,
            column_comment=None,
        )
        table = TableMetadata(
            table_name="users",
            table_comment="用户表",
            engine="InnoDB",
            columns=[col],
        )
        assert table.table_name == "users"
        assert table.table_comment == "用户表"
        assert len(table.columns) == 1


class TestFieldSemantic:
    """FieldSemantic tests"""

    def test_create_field_semantic(self):
        """Test creating field semantic"""
        fs = FieldSemantic(
            id="test_db.users.user_name",
            db_name="test_db",
            table_name="users",
            column_name="user_name",
            data_type="varchar",
            chinese_name="用户名",
            business_definition="用户的登录名称",
            value_rules="唯一，不可为空",
            related_fields=["users.id"],
            data_category=DataCategory.DIMENSION,
            status=ColumnType.CALIBRATED,
        )
        assert fs.column_name == "user_name"
        assert fs.chinese_name == "用户名"
        assert fs.data_category == DataCategory.DIMENSION
        assert fs.status == ColumnType.CALIBRATED

    def test_default_values(self):
        """Test default values"""
        fs = FieldSemantic(
            id="test_db.users.test_col",
            db_name="test_db",
            table_name="users",
            column_name="test_col",
            data_type="varchar",
        )
        assert fs.chinese_name is None
        assert fs.business_definition is None
        assert fs.related_fields == []
        assert fs.data_category == DataCategory.OTHER
        assert fs.status == ColumnType.PENDING


class TestTableSemantic:
    """TableSemantic tests"""

    def test_create_table_semantic(self):
        """Test creating table semantic"""
        fs = FieldSemantic(
            id="test_db.users.id",
            db_name="test_db",
            table_name="users",
            column_name="id",
            data_type="bigint",
        )
        ts = TableSemantic(
            table_name="users",
            db_name="test_db",
            chinese_name="用户表",
            business_definition="存储用户信息",
            data_category=DataCategory.DIMENSION,
            field_semantics=[fs],
        )
        assert ts.table_name == "users"
        assert ts.chinese_name == "用户表"
        assert len(ts.field_semantics) == 1


class TestRelationship:
    """Relationship tests"""

    def test_create_relationship(self):
        """Test creating relationship"""
        rel = Relationship(
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
            relationship_type="many-to-one",
            match_rate=0.95,
            verified=True,
        )
        assert rel.source_table == "orders"
        assert rel.target_table == "users"
        assert rel.match_rate == 0.95
        assert rel.verified is True


class TestRAGContext:
    """RAGContext tests"""

    def test_create_rag_context(self):
        """Test creating RAG context"""
        fs = FieldSemantic(
            id="test_db.users.id",
            db_name="test_db",
            table_name="users",
            column_name="id",
            data_type="bigint",
            chinese_name="用户 ID",
        )
        ts = TableSemantic(
            table_name="users",
            db_name="test_db",
            chinese_name="用户表",
            business_definition="存储用户信息",
            data_category=DataCategory.DIMENSION,
            field_semantics=[fs],
        )
        ctx = RAGContext(
            query="查询用户信息",
            relevant_fields=[fs],
            relevant_tables=[ts],
            relationships=[],
        )
        assert ctx.query == "查询用户信息"
        assert len(ctx.relevant_tables) == 1

    def test_to_prompt(self):
        """Test conversion to prompt"""
        fs = FieldSemantic(
            id="test_db.users.id",
            db_name="test_db",
            table_name="users",
            column_name="id",
            data_type="bigint",
            chinese_name="用户 ID",
            business_definition="主键",
        )
        ts = TableSemantic(
            table_name="users",
            db_name="test_db",
            chinese_name="用户表",
            business_definition="存储用户信息",
            data_category=DataCategory.DIMENSION,
            field_semantics=[fs],
        )
        ctx = RAGContext(
            query="查询用户信息",
            relevant_fields=[fs],
            relevant_tables=[ts],
            relationships=[],
        )
        prompt = ctx.to_prompt()
        assert "users" in prompt
        assert "用户表" in prompt


class TestDataType:
    """Data type tests"""

    def test_column_type_values(self):
        """Test column type enum values"""
        assert ColumnType.PENDING.value == "pending"
        assert ColumnType.CALIBRATED.value == "calibrated"
        assert ColumnType.SKIPPED.value == "skipped"

    def test_data_category_values(self):
        """Test data category enum values"""
        assert DataCategory.DIMENSION.value == "dimension"
        assert DataCategory.METRIC.value == "metric"
        assert DataCategory.FACT.value == "fact"
        assert DataCategory.OTHER.value == "other"
