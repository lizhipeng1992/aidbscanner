"""语义缓存功能测试 - 覆盖分析后存储、缓存读取、更新保存等场景"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime

from app import app
from core.models import DataCategory, ColumnType


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def mock_field_semantic():
    """构造一个标准的字段语义数据"""
    return {
        "id": "test_db.users.email",
        "db_name": "test_db",
        "table_name": "users",
        "column_name": "email",
        "data_type": "varchar",
        "chinese_name": "邮箱地址",
        "business_definition": "用户注册邮箱",
        "value_rules": "标准邮箱格式",
        "related_fields": [],
        "data_category": "dimension",
        "status": "auto",
        "calibrated_by": None,
        "calibrated_at": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }


@pytest.fixture
def mock_field_semantic_obj():
    """构造一个 FieldSemantic 对象"""
    return Mock(
        id="test_db.users.email",
        db_name="test_db",
        table_name="users",
        column_name="email",
        data_type="varchar",
        chinese_name="邮箱地址",
        business_definition="用户注册邮箱",
        value_rules="标准邮箱格式",
        related_fields=[],
        data_category=DataCategory.DIMENSION,
        status=ColumnType.AUTO,
    )


class TestFieldSemanticCacheEndpoint:
    """GET /databases/{db}/tables/{table}/field/{col}/semantic 端点测试"""

    @patch("app.chroma_store")
    def test_cache_hit(self, mock_store, client, mock_field_semantic):
        """测试缓存命中：字段已分析过"""
        mock_store.get_field_semantic.return_value = mock_field_semantic

        response = client.get(
            "/databases/test_db/tables/users/field/email/semantic"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_semantics"] is True
        assert data["chinese_name"] == "邮箱地址"
        assert data["data_category"] == "dimension"
        mock_store.get_field_semantic.assert_called_once_with("test_db.users.email")

    @patch("app.chroma_store")
    def test_cache_miss(self, mock_store, client):
        """测试缓存未命中：字段未分析"""
        mock_store.get_field_semantic.return_value = None

        response = client.get(
            "/databases/test_db/tables/users/field/unknown_col/semantic"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_semantics"] is False
        assert data["column_name"] == "unknown_col"


class TestTableSemanticCacheEndpoint:
    """GET /databases/{db}/tables/{table}/semantic 端点测试"""

    @patch("app.chroma_store")
    def test_table_cache_hit_with_fields(self, mock_store, client):
        """测试表缓存命中：返回所有字段"""
        mock_store.get_table_semantic.return_value = {
            "table_name": "users",
            "db_name": "test_db",
            "chinese_name": "用户表",
            "business_definition": "存储用户信息",
            "data_category": "dimension",
            "fields": [
                {
                    "column_name": "id",
                    "data_type": "bigint",
                    "chinese_name": "用户ID",
                    "business_definition": "用户唯一标识",
                    "value_rules": None,
                    "related_fields": [],
                    "data_category": "dimension",
                    "status": "auto",
                },
                {
                    "column_name": "email",
                    "data_type": "varchar",
                    "chinese_name": "邮箱地址",
                    "business_definition": "用户注册邮箱",
                    "value_rules": "标准邮箱格式",
                    "related_fields": [],
                    "data_category": "dimension",
                    "status": "pending",
                },
            ],
        }

        response = client.get("/databases/test_db/tables/users/semantic")

        assert response.status_code == 200
        data = response.json()
        assert data["has_semantics"] is True
        assert data["chinese_name"] == "用户表"
        assert len(data["fields"]) == 2
        assert data["fields"][0]["column_name"] == "id"
        assert data["fields"][1]["column_name"] == "email"
        assert data["fields"][0]["chinese_name"] == "用户ID"
        # status is converted to ColumnType enum, "pending" -> "pending" string
        assert data["fields"][1]["status"] == "pending"

    @patch("app.chroma_store")
    def test_table_cache_miss(self, mock_store, client):
        """测试表缓存未命中"""
        mock_store.get_table_semantic.return_value = None

        response = client.get("/databases/test_db/tables/nonexistent/semantic")

        assert response.status_code == 200
        data = response.json()
        assert data["has_semantics"] is False
        assert data["fields"] == []

    @patch("app.chroma_store")
    def test_table_cache_empty_fields(self, mock_store, client):
        """测试表缓存存在但字段为空"""
        mock_store.get_table_semantic.return_value = {"fields": []}

        response = client.get("/databases/test_db/tables/empty_table/semantic")

        assert response.status_code == 200
        data = response.json()
        assert data["has_semantics"] is False
        assert data["fields"] == []


class TestFieldAnalyzeStoresToChroma:
    """测试 analyze_field 端点分析后将结果写入 ChromaDB"""

    @patch("app.chroma_store")
    def test_analyze_field_stores_to_chroma(self, mock_store, client, mock_field_semantic_obj):
        """字段分析完成后应写入 ChromaDB，以便后续 update 能找到"""
        mock_store.get_field_semantic.return_value = None  # 缓存未命中

        mock_scanner = Mock()
        mock_scanner.scan_database.return_value = [
            Mock(
                table_name="users",
                table_comment="用户表",
                engine="InnoDB",
                columns=[
                    Mock(
                        column_name="email",
                        table_name="users",
                        data_type="varchar",
                        column_comment=None,
                    )
                ],
            )
        ]
        mock_scanner.get_sample_data.return_value = ["test@example.com"]

        mock_analyzer = Mock()
        mock_analyzer.analyze_field.return_value = mock_field_semantic_obj
        mock_analyzer.storage = Mock()
        mock_analyzer.storage.store_table_semantic = Mock()

        with patch("app.get_scanner", return_value=mock_scanner), \
             patch("app.get_analyzer", return_value=mock_analyzer):
            response = client.post("/fields/analyze", json={
                "db_name": "test_db",
                "table_name": "users",
                "column_name": "email",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["chinese_name"] == "邮箱地址"
        # 验证调用了存储
        mock_analyzer.storage.store_table_semantic.assert_called_once()
        call_args = mock_analyzer.storage.store_table_semantic.call_args[0][0]
        assert call_args.table_name == "users"
        assert len(call_args.field_semantics) == 1
        assert call_args.field_semantics[0].column_name == "email"

    @patch("app.chroma_store")
    def test_analyze_field_cache_hit_no_llm(self, mock_store, client, mock_field_semantic):
        """缓存命中时不应调用 LLM 或存储"""
        mock_store.get_field_semantic.return_value = mock_field_semantic

        response = client.post("/fields/analyze", json={
            "db_name": "test_db",
            "table_name": "users",
            "column_name": "email",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["has_semantics"] is True  # 实际返回的是 FieldSemanticResponse，没有 has_semantics
        assert data["chinese_name"] == "邮箱地址"

    @patch("app.chroma_store")
    def test_analyze_field_storage_failure_does_not_crash(self, mock_store, client, mock_field_semantic_obj):
        """存储失败不应影响分析结果返回"""
        mock_store.get_field_semantic.return_value = None

        mock_scanner = Mock()
        mock_scanner.scan_database.return_value = [
            Mock(
                table_name="users",
                table_comment="用户表",
                engine="InnoDB",
                columns=[
                    Mock(
                        column_name="email",
                        table_name="users",
                        data_type="varchar",
                        column_comment=None,
                    )
                ],
            )
        ]
        mock_scanner.get_sample_data.return_value = ["test@example.com"]

        mock_analyzer = Mock()
        mock_analyzer.analyze_field.return_value = mock_field_semantic_obj
        mock_analyzer.storage = Mock()
        mock_analyzer.storage.store_table_semantic.side_effect = Exception("ChromaDB error")

        with patch("app.get_scanner", return_value=mock_scanner), \
             patch("app.get_analyzer", return_value=mock_analyzer):
            response = client.post("/fields/analyze", json={
                "db_name": "test_db",
                "table_name": "users",
                "column_name": "email",
            })

        # 即使存储失败，分析结果仍应正常返回
        assert response.status_code == 200
        assert response.json()["chinese_name"] == "邮箱地址"


class TestUpdateFieldSemantic:
    """PUT /fields/semantic 端点测试"""

    @patch("app.chroma_store")
    def test_update_field_success(self, mock_store, client, mock_field_semantic):
        """测试字段语义更新成功"""
        mock_store.get_field_semantic.return_value = mock_field_semantic
        mock_store.update_field_semantic.return_value = True

        response = client.put("/fields/semantic", json={
            "field_id": "test_db.users.email",
            "chinese_name": "邮箱（修改后）",
            "business_definition": "用户登录邮箱",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["chinese_name"] == "邮箱（修改后）"

    @patch("app.chroma_store")
    def test_update_field_no_changes(self, mock_store, client, mock_field_semantic):
        """测试用户点了保存但没有修改任何字段 - 应返回成功而非 400"""
        mock_store.get_field_semantic.return_value = mock_field_semantic

        response = client.put("/fields/semantic", json={
            "field_id": "test_db.users.email",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["chinese_name"] == "邮箱地址"

    @patch("app.chroma_store")
    def test_update_field_not_found(self, mock_store, client):
        """测试字段不存在 - 应返回 404"""
        mock_store.get_field_semantic.return_value = None

        response = client.put("/fields/semantic", json={
            "field_id": "test_db.nonexistent.col",
            "chinese_name": "新名称",
        })

        assert response.status_code == 404

    @patch("app.chroma_store")
    def test_update_field_update_chroma(self, mock_store, client, mock_field_semantic):
        """测试更新后 ChromaDB 被正确调用"""
        mock_store.get_field_semantic.return_value = mock_field_semantic
        mock_store.update_field_semantic.return_value = True

        response = client.put("/fields/semantic", json={
            "field_id": "test_db.users.email",
            "data_category": "metric",
        })

        assert response.status_code == 200
        mock_store.update_field_semantic.assert_called_once()
        call_args = mock_store.update_field_semantic.call_args[0]
        field_id = call_args[0]
        updates = call_args[1]
        assert field_id == "test_db.users.email"
        assert updates["data_category"] == "metric"


class TestChromaStoreIntegration:
    """ChromaStore 集成测试 - 验证存储和读取的完整流程"""

    def test_store_and_retrieve_field_semantic(self):
        """测试字段语义的存储和读取"""
        from core.chroma_store import ChromaStore
        from core.models import TableSemantic, FieldSemantic

        store = ChromaStore(path="./data/chroma_test")

        try:
            table_semantic = TableSemantic(
                table_name="test_table",
                db_name="test_db",
                chinese_name="测试表",
                field_semantics=[
                    FieldSemantic(
                        id="test_db.test_table.col1",
                        db_name="test_db",
                        table_name="test_table",
                        column_name="col1",
                        data_type="varchar",
                        chinese_name="列1中文名",
                        business_definition="列1业务定义",
                        data_category=DataCategory.DIMENSION,
                        status=ColumnType.AUTO,
                    ),
                    FieldSemantic(
                        id="test_db.test_table.col2",
                        db_name="test_db",
                        table_name="test_table",
                        column_name="col2",
                        data_type="bigint",
                        chinese_name="列2中文名",
                        business_definition="列2业务定义",
                        data_category=DataCategory.METRIC,
                        status=ColumnType.PENDING,
                    ),
                ],
            )

            # 存储
            store.store_table_semantic(table_semantic)

            # 读取单个字段
            result = store.get_field_semantic("test_db.test_table.col1")
            assert result is not None
            assert result["chinese_name"] == "列1中文名"
            assert result["data_category"] == "dimension"
            assert result["column_name"] == "col1"

            # 读取表级语义
            table_result = store.get_table_semantic("test_db", "test_table")
            assert table_result is not None
            assert table_result["chinese_name"] == "测试表"
            assert len(table_result["fields"]) == 2

            # 更新字段
            store.update_field_semantic(
                "test_db.test_table.col1",
                {"chinese_name": "更新后的中文名"}
            )
            updated = store.get_field_semantic("test_db.test_table.col1")
            assert updated["chinese_name"] == "更新后的中文名"

            # 读取不存在的字段
            missing = store.get_field_semantic("test_db.nonexistent.col")
            assert missing is None

        finally:
            # 清理测试数据
            try:
                store.client.delete_collection("semantics")
            except Exception:
                pass
            # 清理测试目录
            import shutil
            try:
                shutil.rmtree("./data/chroma_test")
            except Exception:
                pass

    def test_store_and_retrieve_field_semantic_with_related_fields(self):
        """测试存储和读取包含关联字段的字段语义"""
        from core.chroma_store import ChromaStore
        from core.models import TableSemantic, FieldSemantic

        store = ChromaStore(path="./data/chroma_test_related")

        try:
            table_semantic = TableSemantic(
                table_name="orders",
                db_name="test_db",
                field_semantics=[
                    FieldSemantic(
                        id="test_db.orders.user_id",
                        db_name="test_db",
                        table_name="orders",
                        column_name="user_id",
                        data_type="bigint",
                        chinese_name="用户ID",
                        business_definition="订单关联的用户",
                        related_fields=["test_db.users.id"],
                        data_category=DataCategory.DIMENSION,
                        status=ColumnType.AUTO,
                    ),
                ],
            )

            store.store_table_semantic(table_semantic)
            result = store.get_field_semantic("test_db.orders.user_id")

            assert result is not None
            assert result["chinese_name"] == "用户ID"
            assert result["related_fields"] == ["test_db.users.id"]

        finally:
            try:
                store.client.delete_collection("semantics")
            except Exception:
                pass
            import shutil
            try:
                shutil.rmtree("./data/chroma_test_related")
            except Exception:
                pass
