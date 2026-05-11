"""Review mode functionality tests"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime

from app import app
from core.models import DataCategory, ColumnType
from core.chroma_store import ChromaStore


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def mock_chroma_store():
    """Mock ChromaStore"""
    with patch("core.chroma_store.ChromaStore") as mock:
        mock_instance = Mock()
        mock.return_value = mock_instance

        # Set default return values
        mock_instance.get_pending_fields.return_value = [
            {
                "field_id": "test_db.users.id",
                "db_name": "test_db",
                "table_name": "users",
                "column_name": "id",
                "data_type": "bigint",
                "chinese_name": "用户 ID",
                "business_definition": "用户的唯一标识",
                "value_rules": "正整数",
                "related_fields": [],
                "data_category": "dimension",
                "created_at": datetime.now().isoformat(),
            }
        ]
        mock_instance.submit_field.return_value = True
        mock_instance.reject_field.return_value = True
        mock_instance.modify_field.return_value = True
        yield mock_instance


class TestReviewPendingEndpoint:
    """GET /review/pending endpoint tests"""

    @patch("app.chroma_store")
    def test_get_pending_success(self, mock_store, client):
        """Test getting pending fields success"""
        mock_store.get_pending_fields.return_value = [
            {
                "field_id": "test_db.users.id",
                "db_name": "test_db",
                "table_name": "users",
                "column_name": "id",
                "data_type": "bigint",
                "chinese_name": "用户 ID",
                "business_definition": "用户的唯一标识",
                "value_rules": "",
                "related_fields": [],
                "data_category": "dimension",
                "created_at": "2024-01-01T00:00:00",
            }
        ]

        response = client.get("/review/pending")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["pending_fields"]) == 1
        assert data["pending_fields"][0]["id"] == "test_db.users.id"

    @patch("app.chroma_store")
    def test_get_pending_with_db_filter(self, mock_store, client):
        """Test filtering pending fields by database"""
        mock_store.get_pending_fields.return_value = []

        response = client.get("/review/pending?db_name=test_db")

        assert response.status_code == 200
        mock_store.get_pending_fields.assert_called_once_with("test_db")

    @patch("app.chroma_store")
    def test_get_pending_empty(self, mock_store, client):
        """Test no pending fields"""
        mock_store.get_pending_fields.return_value = []

        response = client.get("/review/pending")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["pending_fields"] == []


class TestReviewSubmitEndpoint:
    """POST /review/submit endpoint tests"""

    @patch("app.chroma_store")
    def test_submit_success(self, mock_store, client):
        """Test submitting review success"""
        mock_store.submit_field.return_value = True

        response = client.post("/review/submit", json={
            "field_id": "test_db.users.id",
            "calibrated_by": "admin",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "calibrated"
        mock_store.submit_field.assert_called_once_with("test_db.users.id", "admin", None)

    @patch("app.chroma_store")
    def test_submit_with_modifications(self, mock_store, client):
        """Test submitting review with modifications"""
        mock_store.submit_field.return_value = True

        modifications = {
            "chinese_name": "用户编号（修改后）",
            "business_definition": "用户系统唯一编号",
        }

        response = client.post("/review/submit", json={
            "field_id": "test_db.users.id",
            "calibrated_by": "admin",
            "modifications": modifications,
        })

        assert response.status_code == 200
        mock_store.submit_field.assert_called_once_with(
            "test_db.users.id", "admin", modifications
        )

    @patch("app.chroma_store")
    def test_submit_failed(self, mock_store, client):
        """Test submitting review failure"""
        mock_store.submit_field.return_value = False

        response = client.post("/review/submit", json={
            "field_id": "test_db.users.id",
            "calibrated_by": "admin",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["status"] == "pending"

    def test_submit_missing_field_id(self, client):
        """Test missing field_id"""
        response = client.post("/review/submit", json={
            "calibrated_by": "admin",
        })

        assert response.status_code == 422


class TestReviewRejectEndpoint:
    """POST /review/reject endpoint tests"""

    @patch("app.chroma_store")
    def test_reject_success(self, mock_store, client):
        """Test rejecting field success"""
        mock_store.reject_field.return_value = True

        response = client.post("/review/reject", json={
            "field_id": "test_db.users.id",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "skipped"
        mock_store.reject_field.assert_called_once_with("test_db.users.id")

    @patch("app.chroma_store")
    def test_reject_with_reason(self, mock_store, client):
        """Test rejecting field with reason"""
        mock_store.reject_field.return_value = True

        response = client.post("/review/reject", json={
            "field_id": "test_db.users.id",
            "reason": "字段用途不明确",
        })

        assert response.status_code == 200
        mock_store.reject_field.assert_called_once_with("test_db.users.id")

    @patch("app.chroma_store")
    def test_reject_failed(self, mock_store, client):
        """Test rejecting field failure"""
        mock_store.reject_field.return_value = False

        response = client.post("/review/reject", json={
            "field_id": "test_db.users.id",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    def test_reject_missing_field_id(self, client):
        """Test missing field_id"""
        response = client.post("/review/reject", json={})

        assert response.status_code == 422


class TestReviewModifyEndpoint:
    """POST /review/modify endpoint tests"""

    @patch("app.chroma_store")
    def test_modify_success(self, mock_store, client):
        """Test modifying and approving success"""
        mock_store.modify_field.return_value = True

        modifications = {
            "chinese_name": "用户编号（修改后）",
            "business_definition": "用户系统唯一编号",
            "data_category": "dimension",
        }

        response = client.post("/review/modify", json={
            "field_id": "test_db.users.id",
            "calibrated_by": "admin",
            "modifications": modifications,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "calibrated"
        mock_store.modify_field.assert_called_once_with(
            "test_db.users.id", modifications, "admin"
        )

    @patch("app.chroma_store")
    def test_modify_failed(self, mock_store, client):
        """Test modifying and approving failure"""
        mock_store.modify_field.return_value = False

        response = client.post("/review/modify", json={
            "field_id": "test_db.users.id",
            "calibrated_by": "admin",
            "modifications": {"chinese_name": "新名称"},
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    def test_modify_missing_modifications(self, client):
        """Test missing modifications"""
        response = client.post("/review/modify", json={
            "field_id": "test_db.users.id",
            "calibrated_by": "admin",
        })

        assert response.status_code == 422


class TestRuntimeModeConfig:
    """Runtime mode config tests"""

    def test_runtime_mode_default(self):
        """Test runtime_mode default value"""
        from config.settings import settings
        assert settings.runtime_mode == "auto"

    def test_effective_runtime_mode_property(self):
        """Test effective_runtime_mode property"""
        from config.settings import settings
        assert settings.effective_runtime_mode == settings.runtime_mode


class TestSemanticAnalyzerRuntimeMode:
    """Semantic analyzer runtime mode tests"""

    @patch("core.semantic_analyzer.settings")
    @patch("core.semantic_analyzer.ChromaStore")
    def test_auto_mode_status(self, mock_chroma_store, mock_settings):
        """Test auto mode field status is AUTO"""
        from core.semantic_analyzer import SemanticAnalyzer
        from core.llm_client import BaseLLMClient, ChatResponse
        from core.models import ColumnMetadata

        mock_settings.effective_runtime_mode = "auto"
        mock_chroma_store.return_value = Mock()

        mock_llm_client = Mock(spec=BaseLLMClient)
        mock_llm_client.chat.return_value = ChatResponse(
            content='{"chinese_name": "用户 ID", "business_definition": "用户标识", "value_rules": "", "related_fields": [], "data_category": "dimension"}'
        )

        analyzer = SemanticAnalyzer(llm_client=mock_llm_client)
        column = ColumnMetadata(
            column_name="id",
            table_name="users",
            ordinal_position=1,
            data_type="bigint",
            is_nullable="NO",
            column_comment="用户标识",
        )

        semantic = analyzer.analyze_field(column, "users", "test_db")
        assert semantic.status == ColumnType.AUTO

    @patch("core.semantic_analyzer.settings")
    @patch("core.semantic_analyzer.ChromaStore")
    def test_review_mode_status(self, mock_chroma_store, mock_settings):
        """Test review mode field status is PENDING"""
        from core.semantic_analyzer import SemanticAnalyzer
        from core.llm_client import BaseLLMClient, ChatResponse
        from core.models import ColumnMetadata

        mock_settings.effective_runtime_mode = "review"
        mock_chroma_store.return_value = Mock()

        mock_llm_client = Mock(spec=BaseLLMClient)
        mock_llm_client.chat.return_value = ChatResponse(
            content='{"chinese_name": "用户 ID", "business_definition": "用户标识", "value_rules": "", "related_fields": [], "data_category": "dimension"}'
        )

        analyzer = SemanticAnalyzer(llm_client=mock_llm_client)
        column = ColumnMetadata(
            column_name="id",
            table_name="users",
            ordinal_position=1,
            data_type="bigint",
            is_nullable="NO",
            column_comment="用户标识",
        )

        semantic = analyzer.analyze_field(column, "users", "test_db")
        assert semantic.status == ColumnType.PENDING
