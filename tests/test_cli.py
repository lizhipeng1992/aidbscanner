"""CLI 命令行接口单元测试"""
import pytest
from unittest.mock import Mock, patch
from click.testing import CliRunner

from cli import cli


@pytest.fixture
def runner():
    """创建 CLI 测试运行器"""
    return CliRunner()


class TestHealthCommand:
    """health 命令测试"""

    @patch("builtins.ollama", create=True)
    @patch("cli.get_scanner")
    def test_health_success(self, mock_get_scanner, mock_ollama, runner):
        """测试健康检查成功"""
        mock_scanner = Mock()
        mock_get_scanner.return_value = mock_scanner
        mock_scanner.list_databases.return_value = ["test"]

        mock_client = Mock()
        mock_ollama.Client.return_value = mock_client

        response = runner.invoke(cli, ["health"])

        assert response.exit_code == 0
        assert "status" in response.output
        assert "mysql" in response.output

    @patch("builtins.ollama", create=True)
    @patch("cli.get_scanner")
    def test_health_unhealthy(self, mock_get_scanner, mock_ollama, runner):
        """测试健康检查失败"""
        from mysql.connector import Error as MySQLError
        mock_get_scanner.side_effect = MySQLError("Connection refused")
        mock_ollama.Client.return_value = Mock()

        response = runner.invoke(cli, ["health"])

        assert response.exit_code == 0
        assert "unhealthy" in response.output


class TestDatabasesCommand:
    """databases 命令测试"""

    @patch("cli.MySQLScanner.list_databases")
    def test_databases_success(self, mock_list, runner):
        """测试列出数据库成功"""
        mock_list.return_value = ["test_db", "prod_db", "mysql"]

        response = runner.invoke(cli, ["databases"])

        assert response.exit_code == 0
        assert "test_db" in response.output
        assert "prod_db" in response.output
        assert "mysql" not in response.output  # 系统数据库被过滤

    @patch("cli.MySQLScanner.list_databases")
    def test_databases_error(self, mock_list, runner):
        """测试列出数据库失败"""
        from mysql.connector import Error as MySQLError
        mock_list.side_effect = MySQLError("Connection failed")

        response = runner.invoke(cli, ["databases"])

        assert response.exit_code == 1
        assert "错误" in response.output


class TestTablesCommand:
    """tables 命令测试"""

    @patch("cli.MySQLScanner.scan_database")
    def test_tables_success(self, mock_scan, runner):
        """测试列出表成功"""
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

        response = runner.invoke(cli, ["tables", "test_db"])

        assert response.exit_code == 0
        assert "users" in response.output
        assert "用户表" in response.output

    @patch("cli.MySQLScanner.scan_database")
    def test_tables_not_found(self, mock_scan, runner):
        """测试数据库不存在"""
        mock_scan.return_value = []

        response = runner.invoke(cli, ["tables", "nonexistent"])

        assert response.exit_code == 1
        assert "不存在" in response.output


class TestFieldCommand:
    """field 命令测试"""

    @patch("cli.SemanticAnalyzer.analyze_field")
    @patch("cli.MySQLScanner.get_sample_data")
    @patch("cli.MySQLScanner.scan_table_only")
    def test_field_success(self, mock_scan, mock_samples, mock_analyze, runner):
        """测试字段分析成功"""
        from core.models import TableMetadata, ColumnMetadata, FieldSemantic, DataCategory, ColumnType

        mock_scan.return_value = TableMetadata(
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

        response = runner.invoke(cli, ["field", "test_db", "users", "id"])

        assert response.exit_code == 0
        assert "用户 ID" in response.output
        assert "dimension" in response.output


class TestAnalyzeCommand:
    """analyze 命令测试"""

    @patch("cli.SemanticAnalyzer.analyze_table")
    @patch("cli.MySQLScanner.scan_table_only")
    def test_analyze_success(self, mock_scan, mock_analyze, runner):
        """测试表分析成功"""
        from core.models import TableMetadata, ColumnMetadata, TableSemantic, FieldSemantic, DataCategory, ColumnType

        mock_scan.return_value = TableMetadata(
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

        response = runner.invoke(cli, ["analyze", "test_db", "users", "--sample-size", "5"])

        assert response.exit_code == 0
        assert "用户表" in response.output


class TestScanCommand:
    """scan 命令测试"""

    @patch("cli.SemanticAnalyzer.batch_analyze_tables")
    @patch("cli.MySQLScanner.scan_database")
    def test_scan_success(self, mock_scan, mock_batch, runner):
        """测试全量扫描成功"""
        from core.models import TableMetadata, ColumnMetadata, TableSemantic, FieldSemantic, DataCategory, ColumnType

        mock_scan.return_value = [
            TableMetadata(
                table_name="users",
                table_comment="用户表",
                engine="InnoDB",
                columns=[],
            )
        ]
        mock_batch.return_value = [
            TableSemantic(
                table_name="users",
                db_name="test_db",
                chinese_name="用户表",
                business_definition="存储用户信息",
                data_category=DataCategory.DIMENSION,
                field_semantics=[],
            )
        ]

        response = runner.invoke(cli, ["scan", "test_db", "--sample-size", "5"])

        assert response.exit_code == 0
        assert "test_db" in response.output


class TestReviewPendingCommand:
    """review-pending 命令测试"""

    @patch("cli.get_pending_fields")
    def test_review_pending_success(self, mock_get_pending, runner):
        """测试列出待审核字段成功"""
        mock_get_pending.return_value = [
            {
                "field_id": "test_db.users.id",
                "chinese_name": "用户 ID",
                "business_definition": "用户的唯一标识",
                "data_category": "dimension",
                "created_at": "2024-01-01T00:00:00",
            }
        ]

        response = runner.invoke(cli, ["review-pending"])

        assert response.exit_code == 0
        assert "待审核字段列表" in response.output
        assert "test_db.users.id" in response.output
        assert "用户 ID" in response.output

    @patch("cli.get_pending_fields")
    def test_review_pending_empty(self, mock_get_pending, runner):
        """测试无待审核字段"""
        mock_get_pending.return_value = []

        response = runner.invoke(cli, ["review-pending"])

        assert response.exit_code == 0
        assert "暂无待审核字段" in response.output

    @patch("cli.get_pending_fields")
    def test_review_pending_with_db_filter(self, mock_get_pending, runner):
        """测试按数据库过滤"""
        mock_get_pending.return_value = []

        response = runner.invoke(cli, ["review-pending", "--db-name", "test_db"])

        assert response.exit_code == 0
        mock_get_pending.assert_called_once_with("test_db")


class TestReviewSubmitCommand:
    """review-submit 命令测试"""

    @patch("cli.get_storage")
    def test_review_submit_success(self, mock_get_storage, runner):
        """测试批量确认字段成功"""
        mock_storage = Mock()
        mock_get_storage.return_value = mock_storage
        mock_storage.submit_field.return_value = True

        response = runner.invoke(
            cli,
            ["review-submit", "test_db.users.id", "test_db.orders.user_id", "--calibrated-by", "admin"]
        )

        assert response.exit_code == 0
        assert "已确认" in response.output
        assert mock_storage.submit_field.call_count == 2

    @patch("cli.get_storage")
    def test_review_submit_failed(self, mock_get_storage, runner):
        """测试确认字段失败"""
        mock_storage = Mock()
        mock_get_storage.return_value = mock_storage
        mock_storage.submit_field.return_value = False

        response = runner.invoke(cli, ["review-submit", "test_db.users.id"])

        assert response.exit_code == 0
        assert "确认失败" in response.output


class TestReviewRejectCommand:
    """review-reject 命令测试"""

    @patch("cli.get_storage")
    def test_review_reject_success(self, mock_get_storage, runner):
        """测试拒绝字段成功"""
        mock_storage = Mock()
        mock_get_storage.return_value = mock_storage
        mock_storage.reject_field.return_value = True

        response = runner.invoke(cli, ["review-reject", "test_db.users.id"])

        assert response.exit_code == 0
        assert "已拒绝" in response.output
        mock_storage.reject_field.assert_called_once_with("test_db.users.id")

    @patch("cli.get_storage")
    def test_review_reject_failed(self, mock_get_storage, runner):
        """测试拒绝字段失败"""
        mock_storage = Mock()
        mock_get_storage.return_value = mock_storage
        mock_storage.reject_field.return_value = False

        response = runner.invoke(cli, ["review-reject", "test_db.users.id"])

        assert response.exit_code == 0
        assert "拒绝失败" in response.output


class TestReviewModifyCommand:
    """review-modify 命令测试"""

    @patch("cli.get_storage")
    def test_review_modify_success(self, mock_get_storage, runner):
        """测试修改并确认字段成功"""
        mock_storage = Mock()
        mock_get_storage.return_value = mock_storage
        mock_storage.modify_field.return_value = True

        response = runner.invoke(
            cli,
            [
                "review-modify", "test_db.users.id",
                "--chinese-name", "用户编号",
                "--business-definition", "用户系统唯一编号",
                "--data-category", "dimension",
                "--calibrated-by", "admin"
            ]
        )

        assert response.exit_code == 0
        assert "已修改并确认" in response.output
        mock_storage.modify_field.assert_called_once()

    @patch("cli.get_storage")
    def test_review_modify_failed(self, mock_get_storage, runner):
        """测试修改并确认字段失败"""
        mock_storage = Mock()
        mock_get_storage.return_value = mock_storage
        mock_storage.modify_field.return_value = False

        response = runner.invoke(
            cli,
            [
                "review-modify", "test_db.users.id",
                "--chinese-name", "用户编号",
                "--calibrated-by", "admin"
            ]
        )

        assert response.exit_code == 0
        assert "修改失败" in response.output

