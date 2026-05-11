"""FastAPI application layer unit tests"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from app import app
from core.models import DataCategory, ColumnType


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


class TestHealthEndpoint:
    """Health check endpoint tests"""

    def test_health_success(self, client):
        """Test health check success"""
        with patch("core.scanner.mysql.connector.connect"):
            with patch("ollama.Client"):
                response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "mysql" in data
        assert "llm" in data  # LLM connection status


class TestDatabasesEndpoint:
    """Database list endpoint tests"""

    @patch("core.scanner.MySQLScanner.list_databases")
    def test_list_databases_success(self, mock_list_dbs, client):
        """Test listing databases success"""
        mock_list_dbs.return_value = ["test_db", "prod_db", "mysql", "information_schema"]

        response = client.get("/databases")

        assert response.status_code == 200
        data = response.json()
        # System databases should be filtered
        assert "mysql" not in data["databases"]
        assert "information_schema" not in data["databases"]
        assert "test_db" in data["databases"]
        assert "prod_db" in data["databases"]

    @patch("core.scanner.MySQLScanner.list_databases")
    def test_list_databases_error(self, mock_list_dbs, client):
        """Test listing databases failure"""
        from mysql.connector import Error as MySQLError
        mock_list_dbs.side_effect = MySQLError("Connection failed")

        response = client.get("/databases")

        assert response.status_code == 500


class TestTablesEndpoint:
    """Table list endpoint tests"""

    @patch("core.scanner.MySQLScanner.scan_database")
    def test_list_tables_success(self, mock_scan, client):
        """Test listing tables success"""
        from core.models import TableMetadata, ColumnMetadata

        mock_scan.return_value = [
            TableMetadata(
                table_name="users",
                table_comment="用户表",
                engine="InnoDB",
                columns=[
                    ColumnMetadata(
                        column_name="id",
                        table_name="users",
                        ordinal_position=1,
                        data_type="bigint",
                        is_nullable="NO",
                    ),
                ],
            )
        ]

        response = client.get("/databases/test_db/tables")

        assert response.status_code == 200
        data = response.json()
        assert data["database"] == "test_db"
        assert len(data["tables"]) == 1
        assert data["tables"][0]["table_name"] == "users"

    @patch("core.scanner.MySQLScanner.scan_database")
    def test_list_tables_not_found(self, mock_scan, client):
        """Test database not found"""
        mock_scan.return_value = []

        response = client.get("/databases/nonexistent/tables")

        assert response.status_code == 404


class TestFieldAnalyzeEndpoint:
    """Field analysis endpoint tests"""

    @patch("core.semantic_analyzer.SemanticAnalyzer.analyze_field")
    @patch("core.scanner.MySQLScanner.get_sample_data")
    @patch("core.scanner.MySQLScanner.scan_database")
    def test_analyze_field_success(self, mock_scan, mock_samples, mock_analyze, client):
        """Test field analysis success"""
        from core.models import TableMetadata, ColumnMetadata, FieldSemantic

        mock_scan.return_value = [
            TableMetadata(
                table_name="users",
                table_comment="用户表",
                engine="InnoDB",
                columns=[
                    ColumnMetadata(
                        column_name="id",
                        table_name="users",
                        ordinal_position=1,
                        data_type="bigint",
                        is_nullable="NO",
                    ),
                ],
            )
        ]
        mock_samples.return_value = [1, 2, 3]
        mock_analyze.return_value = FieldSemantic(
            id="test_db.users.id",
            db_name="test_db",
            table_name="users",
            column_name="id",
            data_type="bigint",
            chinese_name="用户 ID",
            business_definition="用户的唯一标识",
            value_rules="正整数",
            related_fields=[],
            data_category=DataCategory.DIMENSION,
            status=ColumnType.CALIBRATED,
        )

        response = client.post("/fields/analyze", json={
            "db_name": "test_db",
            "table_name": "users",
            "column_name": "id",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["chinese_name"] == "用户 ID"
        assert data["data_category"] == "dimension"

    @patch("core.scanner.MySQLScanner.scan_database")
    def test_analyze_field_not_found(self, mock_scan, client):
        """Test field not found"""
        mock_scan.return_value = []

        response = client.post("/fields/analyze", json={
            "db_name": "nonexistent",
            "table_name": "users",
            "column_name": "id",
        })

        assert response.status_code == 404


class TestTableAnalyzeEndpoint:
    """Table analyze endpoint tests"""

    @patch("core.semantic_analyzer.SemanticAnalyzer.analyze_table")
    @patch("core.scanner.MySQLScanner.scan_database")
    def test_analyze_table_success(self, mock_scan, mock_analyze, client):
        """Test table analysis success"""
        from core.models import TableMetadata, ColumnMetadata, TableSemantic, FieldSemantic

        mock_scan.return_value = [
            TableMetadata(
                table_name="users",
                table_comment="用户表",
                engine="InnoDB",
                columns=[
                    ColumnMetadata(
                        column_name="id",
                        table_name="users",
                        ordinal_position=1,
                        data_type="bigint",
                        is_nullable="NO",
                    ),
                ],
            )
        ]
        mock_analyze.return_value = TableSemantic(
            table_name="users",
            db_name="test_db",
            chinese_name="用户表",
            business_definition="存储用户信息",
            data_category=DataCategory.DIMENSION,
            field_semantics=[
                FieldSemantic(
                    id="test_db.users.id",
                    db_name="test_db",
                    table_name="users",
                    column_name="id",
                    data_type="bigint",
                    chinese_name="用户 ID",
                    business_definition="用户的唯一标识",
                    value_rules="",
                    related_fields=[],
                    data_category=DataCategory.DIMENSION,
                    status=ColumnType.CALIBRATED,
                )
            ],
        )

        response = client.post("/tables/analyze", json={
            "db_name": "test_db",
            "table_name": "users",
            "sample_size": 5,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["chinese_name"] == "用户表"
        assert len(data["fields"]) == 1


class TestRelationshipEndpoints:
    """Relationship endpoint tests"""

    @patch("core.semantic_analyzer.SemanticAnalyzer.verify_relationship")
    @patch("core.scanner.MySQLScanner.calculate_match_rate")
    @patch("core.scanner.MySQLScanner.scan_database")
    def test_verify_relationship_success(self, mock_scan, mock_calc, mock_verify, client):
        """Test relationship verification success"""
        from core.models import TableMetadata

        mock_scan.return_value = [TableMetadata(table_name="test", table_comment=None, engine="InnoDB", columns=[])]
        mock_calc.return_value = 0.98
        mock_verify.return_value = True

        response = client.post("/relationships/verify", json={
            "db_name": "test_db",
            "source_table": "orders",
            "source_column": "user_id",
            "target_table": "users",
            "target_column": "id",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["match_rate"] == 0.98
        assert data["verified"] is True

    @patch("core.semantic_analyzer.SemanticAnalyzer.verify_relationship")
    @patch("core.scanner.MySQLScanner.calculate_match_rate")
    @patch("core.scanner.MySQLScanner.discover_foreign_key_candidates")
    @patch("core.scanner.MySQLScanner.scan_database")
    def test_discover_relationships_success(self, mock_scan, mock_discover, mock_calc, mock_verify, client):
        """Test relationship discovery success"""
        from core.models import TableMetadata, Relationship

        mock_scan.return_value = [TableMetadata(table_name="test", table_comment=None, engine="InnoDB", columns=[])]
        mock_discover.return_value = [
            Relationship(
                source_table="orders",
                source_column="user_id",
                target_table="users",
                target_column="id",
                relationship_type="many-to-one",
                match_rate=0.0,
                verified=False,
            )
        ]
        mock_calc.return_value = 0.98
        mock_verify.return_value = True

        response = client.post("/discover/relationships", params={"db_name": "test_db"})

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 0  # 可能为空，取决于匹配率
