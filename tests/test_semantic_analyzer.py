"""语义分析器单元测试"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from core.semantic_analyzer import SemanticAnalyzer
from core.scanner import MySQLScanner
from core.models import ColumnMetadata, TableMetadata, Relationship, DataCategory, ColumnType
from core.llm_client import LLMProvider, BaseLLMClient, ChatResponse
from ollama import RequestError


class TestSemanticAnalyzer:
    """SemanticAnalyzer 测试"""

    def test_analyzer_initialization(self):
        """测试分析器初始化"""
        with patch("core.semantic_analyzer.ChromaStore"):
            analyzer = SemanticAnalyzer()
            assert analyzer is not None
            assert analyzer.scanner is None
            assert analyzer._llm_client is None
            assert analyzer.storage is not None  # ChromaDB 存储已初始化

    @patch("core.semantic_analyzer.ChromaStore")
    def test_analyzer_with_scanner(self, mock_chroma_store):
        """测试带扫描器的分析器初始化"""
        scanner = MySQLScanner()
        analyzer = SemanticAnalyzer(scanner=scanner)
        assert analyzer.scanner == scanner

    @patch("core.semantic_analyzer.ChromaStore")
    def test_get_system_prompt(self, mock_chroma_store):
        """测试系统提示词"""
        analyzer = SemanticAnalyzer()
        prompt = analyzer._get_system_prompt()
        assert "数据语义专家" in prompt
        assert "JSON" in prompt

    @patch("core.semantic_analyzer.ChromaStore")
    def test_build_field_prompt(self, mock_chroma_store):
        """测试构建字段提示词"""
        analyzer = SemanticAnalyzer()
        column = ColumnMetadata(
            column_name="user_id",
            table_name="orders",
            ordinal_position=1,
            data_type="bigint",
            is_nullable="NO",
            column_default=None,
            column_comment="用户 ID",
            is_primary_key=True,
            is_auto_increment=True,
        )

        prompt = analyzer._build_field_prompt(column, "orders", "test_db", [1, 2, 3])

        assert "test_db" in prompt
        assert "orders" in prompt
        assert "user_id" in prompt
        assert "bigint" in prompt
        assert "用户 ID" in prompt
        assert "是否主键：是" in prompt
        assert "是否自增：是" in prompt
        assert "1. 1" in prompt  # 示例值

    @patch("core.semantic_analyzer.ChromaStore")
    def test_parse_semantic_response_valid_json(self, mock_chroma_store):
        """测试解析有效 JSON 响应"""
        analyzer = SemanticAnalyzer()
        response = '{"chinese_name": "用户标识", "business_definition": "用户的唯一标识", "data_category": "dimension"}'

        result = analyzer._parse_semantic_response(response)

        assert result["chinese_name"] == "用户标识"
        assert result["data_category"] == "dimension"

    @patch("core.semantic_analyzer.ChromaStore")
    def test_parse_semantic_response_with_markdown(self, mock_chroma_store):
        """测试解析带 Markdown 标记的 JSON 响应"""
        analyzer = SemanticAnalyzer()
        response = """Here is the result:
```json
{"chinese_name": "订单编号", "business_definition": "订单的唯一编号", "data_category": "fact"}
```"""

        result = analyzer._parse_semantic_response(response)

        assert result["chinese_name"] == "订单编号"

    @patch("core.semantic_analyzer.ChromaStore")
    def test_parse_semantic_response_invalid(self, mock_chroma_store):
        """测试解析无效 JSON 响应"""
        analyzer = SemanticAnalyzer()
        response = "这不是有效的 JSON 格式"

        result = analyzer._parse_semantic_response(response)

        assert result == {}

    @patch("core.semantic_analyzer.ChromaStore")
    def test_create_default_semantic(self, mock_chroma_store):
        """测试创建默认语义"""
        analyzer = SemanticAnalyzer()
        column = ColumnMetadata(
            column_name="created_at",
            table_name="orders",
            ordinal_position=1,
            data_type="datetime",
            is_nullable="NO",
            column_default="CURRENT_TIMESTAMP",
            column_comment="创建时间",
        )

        semantic = analyzer._create_default_semantic(column, "orders", "test_db")

        assert semantic.id == "test_db.orders.created_at"
        assert semantic.column_name == "created_at"
        assert semantic.data_type == "datetime"
        assert semantic.chinese_name == "created_at"
        assert semantic.business_definition == "创建时间"
        assert semantic.data_category == DataCategory.OTHER
        assert semantic.status == ColumnType.PENDING

    @patch("core.semantic_analyzer.ChromaStore")
    def test_analyze_field_success(self, mock_chroma_store):
        """测试字段分析成功"""
        # Mock ChromaStore 实例
        mock_store_instance = Mock()
        mock_chroma_store.return_value = mock_store_instance

        # 创建带 mock LLM 客户端的分析器
        mock_llm_client = Mock(spec=BaseLLMClient)
        mock_llm_client.chat.return_value = ChatResponse(
            content='{"chinese_name": "用户 ID", "business_definition": "用户的唯一标识", "value_rules": "正整数", "related_fields": ["users.id"], "data_category": "dimension"}'
        )

        analyzer = SemanticAnalyzer(llm_client=mock_llm_client)
        column = ColumnMetadata(
            column_name="user_id",
            table_name="orders",
            ordinal_position=1,
            data_type="bigint",
            is_nullable="NO",
            column_comment=None,
        )

        semantic = analyzer.analyze_field(column, "orders", "test_db", [1, 2, 3])

        assert semantic.column_name == "user_id"
        assert semantic.chinese_name == "用户 ID"
        assert semantic.business_definition == "用户的唯一标识"
        assert semantic.data_category == DataCategory.DIMENSION

    @patch("core.semantic_analyzer.settings")
    @patch("core.semantic_analyzer.ChromaStore")
    def test_analyze_field_ollama_error(self, mock_chroma_store, mock_settings):
        """测试字段分析 LLM 错误"""
        from core.llm_client import LLMError

        # Mock settings 为 review 模式
        mock_settings.effective_runtime_mode = "review"

        # Mock ChromaStore 实例
        mock_store_instance = Mock()
        mock_chroma_store.return_value = mock_store_instance

        # 创建带 mock LLM 客户端的分析器（抛出错误）
        mock_llm_client = Mock(spec=BaseLLMClient)
        mock_llm_client.chat.side_effect = LLMError("Connection failed")

        analyzer = SemanticAnalyzer(llm_client=mock_llm_client)
        column = ColumnMetadata(
            column_name="user_id",
            table_name="orders",
            ordinal_position=1,
            data_type="bigint",
            is_nullable="NO",
            column_comment="用户标识",
        )

        semantic = analyzer.analyze_field(column, "orders", "test_db")

        # 应该返回默认语义
        assert semantic.column_name == "user_id"
        assert semantic.chinese_name == "user_id"
        assert semantic.business_definition == "用户标识"
        assert semantic.status == ColumnType.PENDING

    @patch("core.semantic_analyzer.ChromaStore")
    def test_analyze_table_success(self, mock_chroma_store):
        """测试表分析成功"""
        # Mock ChromaStore 实例
        mock_store_instance = Mock()
        mock_chroma_store.return_value = mock_store_instance

        # 创建带 mock LLM 客户端的分析器
        mock_llm_client = Mock(spec=BaseLLMClient)
        mock_llm_client.chat.side_effect = [
            # 表分析响应
            ChatResponse(content='{"chinese_name": "订单表", "business_definition": "存储订单信息", "data_category": "fact"}'),
            # 批量字段分析响应（JSON 数组）
            ChatResponse(content='[{"column_name": "id", "chinese_name": "订单 ID", "business_definition": "订单唯一标识", "value_rules": "", "related_fields": [], "data_category": "dimension"}]'),
        ]

        analyzer = SemanticAnalyzer(llm_client=mock_llm_client)
        table = TableMetadata(
            table_name="orders",
            table_comment="订单信息表",
            engine="InnoDB",
            columns=[
                ColumnMetadata(
                    column_name="id",
                    table_name="orders",
                    ordinal_position=1,
                    data_type="bigint",
                    is_nullable="NO",
                    column_comment="订单 ID",
                    is_primary_key=True,
                ),
            ],
        )

        table_semantic = analyzer.analyze_table(table, "test_db")

        assert table_semantic.table_name == "orders"
        assert table_semantic.chinese_name == "订单表"
        assert table_semantic.data_category == DataCategory.FACT
        assert len(table_semantic.field_semantics) == 1
        assert table_semantic.field_semantics[0].chinese_name == "订单 ID"

    @patch("core.semantic_analyzer.ChromaStore")
    def test_verify_relationship_valid(self, mock_chroma_store):
        """测试关系验证通过"""
        # Mock ChromaStore 实例
        mock_store_instance = Mock()
        mock_chroma_store.return_value = mock_store_instance

        # 创建带 mock LLM 客户端的分析器
        mock_llm_client = Mock(spec=BaseLLMClient)
        mock_llm_client.chat.return_value = ChatResponse(
            content='{"is_valid": true, "reason": "命名规则和匹配率都支持外键关系"}'
        )

        analyzer = SemanticAnalyzer(llm_client=mock_llm_client)
        rel = Relationship(
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
            relationship_type="many-to-one",
            match_rate=0.98,
            verified=False,
        )

        is_valid = analyzer.verify_relationship(rel)

        assert is_valid is True

    @patch("core.semantic_analyzer.ChromaStore")
    def test_verify_relationship_invalid(self, mock_chroma_store):
        """测试关系验证失败"""
        # Mock ChromaStore 实例
        mock_store_instance = Mock()
        mock_chroma_store.return_value = mock_store_instance

        # 创建带 mock LLM 客户端的分析器
        mock_llm_client = Mock(spec=BaseLLMClient)
        mock_llm_client.chat.return_value = ChatResponse(
            content='{"is_valid": false, "reason": "匹配率过低"}'
        )

        analyzer = SemanticAnalyzer(llm_client=mock_llm_client)
        rel = Relationship(
            source_table="orders",
            source_column="product_id",
            target_table="categories",
            target_column="id",
            relationship_type="many-to-one",
            match_rate=0.3,
            verified=False,
        )

        is_valid = analyzer.verify_relationship(rel)

        assert is_valid is False

    @patch("core.semantic_analyzer.ChromaStore")
    def test_verify_relationship_ollama_error(self, mock_chroma_store):
        """测试关系验证 LLM 错误时回退到匹配率判断"""
        from core.llm_client import LLMError

        # Mock ChromaStore 实例
        mock_store_instance = Mock()
        mock_chroma_store.return_value = mock_store_instance

        # 创建带 mock LLM 客户端的分析器（抛出错误）
        mock_llm_client = Mock(spec=BaseLLMClient)
        mock_llm_client.chat.side_effect = LLMError("Connection failed")

        analyzer = SemanticAnalyzer(llm_client=mock_llm_client)

        # 高匹配率应该通过
        rel_high = Relationship(
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
            relationship_type="many-to-one",
            match_rate=0.98,
            verified=False,
        )
        assert analyzer.verify_relationship(rel_high) is True

        # 低匹配率应该失败
        rel_low = Relationship(
            source_table="orders",
            source_column="random_id",
            target_table="users",
            target_column="id",
            relationship_type="many-to-one",
            match_rate=0.5,
            verified=False,
        )
        assert analyzer.verify_relationship(rel_low) is False
