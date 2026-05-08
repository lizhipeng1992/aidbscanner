"""MySQL 扫描器单元测试"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from mysql.connector import Error as MySQLError

from core.scanner import MySQLScanner
from core.models import TableMetadata, ColumnMetadata, Relationship, RelationshipDiscoveryMethod


class TestMySQLScanner:
    """MySQLScanner 测试"""

    def test_scanner_initialization(self):
        """测试扫描器初始化"""
        scanner = MySQLScanner()
        assert scanner is not None
        assert scanner._connection is None

    def test_context_manager_enter(self):
        """测试上下文管理器进入"""
        with patch("mysql.connector.connect") as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            scanner = MySQLScanner()
            # __enter__ 不建立连接，连接在第一次使用时建立
            with scanner:
                assert scanner._connection is None

    def test_context_manager_exit(self):
        """测试上下文管理器退出"""
        with patch("mysql.connector.connect") as mock_connect:
            mock_conn = Mock()
            mock_conn.is_connected.return_value = True
            mock_connect.return_value = mock_conn

            scanner = MySQLScanner()
            with scanner:
                # 触发连接建立
                scanner._get_connection("test_db")

            mock_conn.close.assert_called_once()

    def test_list_databases(self):
        """测试列出数据库"""
        with patch("core.scanner.mysql.connector.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = [
                ("database1",),
                ("database2",),
                ("mysql",),
                ("information_schema",),
            ]
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            scanner = MySQLScanner()
            with scanner:
                databases = scanner.list_databases()

            assert len(databases) == 4
            assert "database1" in databases
            assert "database2" in databases
            assert "mysql" in databases

    def test_scan_database(self):
        """测试扫描数据库"""
        with patch("mysql.connector.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.is_connected.return_value = True
            mock_connect.return_value = mock_conn

            # SHOW TABLE STATUS 返回字典格式 (dictionary=True)
            mock_cursor.fetchone.return_value = {
                "Name": "users",
                "Engine": "InnoDB",
                "Comment": "用户表",
            }

            call_count = [0]

            def mock_execute_side_effect(sql):
                call_count[0] += 1
                return mock_cursor

            def mock_fetchall_side_effect():
                if call_count[0] == 1:  # SHOW TABLES
                    return [{"Tables_in_test_db": "users"}]
                elif call_count[0] == 2:  # SHOW TABLE STATUS (fetchone 已处理)
                    return []
                elif call_count[0] == 3:  # SHOW FULL COLUMNS
                    return [
                        {"Field": "id", "Type": "bigint", "Null": "NO", "Key": "PRI", "Default": None, "Extra": "auto_increment", "Comment": "用户 ID"},
                        {"Field": "name", "Type": "varchar(255)", "Null": "YES", "Key": "", "Default": None, "Extra": "", "Comment": "用户名称"},
                    ]
                elif call_count[0] == 4:  # INFORMATION_SCHEMA.STATISTICS (primary keys)
                    return [{"COLUMN_NAME": "id"}]
                else:  # INFORMATION_SCHEMA.COLUMNS (auto_increment)
                    return [{"COLUMN_NAME": "id"}]

            mock_cursor.execute.side_effect = mock_execute_side_effect
            mock_cursor.fetchall.side_effect = mock_fetchall_side_effect

            scanner = MySQLScanner()
            with scanner:
                tables = scanner.scan_database("test_db")

            assert len(tables) == 1
            assert tables[0].table_name == "users"
            assert tables[0].table_comment == "用户表"
            assert tables[0].engine == "InnoDB"
            assert len(tables[0].columns) == 2

    def test_scan_database_empty(self):
        """测试扫描空数据库"""
        with patch("mysql.connector.connect") as mock_connect:
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = []
            mock_connect.return_value.cursor.return_value.__enter__.return_value = mock_cursor

            scanner = MySQLScanner()
            with scanner:
                tables = scanner.scan_database("empty_db")

            assert tables == []

    def test_get_sample_data(self):
        """测试获取示例数据"""
        with patch("mysql.connector.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.execute.return_value = mock_cursor
            mock_cursor.fetchall.return_value = [
                ("value1",),
                ("value2",),
                ("value3",),
            ]
            mock_connect.return_value = mock_conn

            scanner = MySQLScanner()
            with scanner:
                samples = scanner.get_sample_data("test_db", "users", "name", limit=5)

            assert len(samples) == 3
            assert samples[0] == "value1"

    def test_get_sample_data_with_nulls(self):
        """测试获取示例数据（包含 NULL）"""
        with patch("mysql.connector.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.execute.return_value = mock_cursor
            mock_cursor.fetchall.return_value = [
                ("value1",),
                (None,),
                ("value2",),
                (None,),
            ]
            mock_connect.return_value = mock_conn

            scanner = MySQLScanner()
            with scanner:
                samples = scanner.get_sample_data("test_db", "users", "name", limit=5)

            # 应该过滤掉 NULL 值
            assert len(samples) == 2
            assert None not in samples

    def test_discover_foreign_key_candidates(self):
        """测试发现外键候选"""
        tables = [
            TableMetadata(
                table_name="orders",
                table_comment="订单表",
                engine="InnoDB",
                columns=[
                    ColumnMetadata(
                        column_name="id",
                        table_name="orders",
                        ordinal_position=1,
                        data_type="bigint",
                        is_nullable="NO",
                        column_default=None,
                        column_comment=None,
                    ),
                    ColumnMetadata(
                        column_name="user_id",
                        table_name="orders",
                        ordinal_position=2,
                        data_type="bigint",
                        is_nullable="NO",
                        column_default=None,
                        column_comment="用户 ID",
                    ),
                ],
            ),
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
                        column_default=None,
                        column_comment=None,
                    ),
                ],
            ),
        ]

        with patch("mysql.connector.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.execute.return_value = mock_cursor
            # calculate_match_rate: src=100, match=95 (2 fetchone)
            # calculate_value_overlap: src=100, tgt=200, intersection=95 (3 fetchone)
            mock_cursor.fetchone.side_effect = [
                (100,), (95,),   # match_rate
                (100,), (200,), (95,),  # value_overlap
            ]
            mock_connect.return_value = mock_conn

            scanner = MySQLScanner()
            candidates = scanner.discover_foreign_key_candidates("test_db", tables)

        assert len(candidates) == 1
        assert candidates[0].source_table == "orders"
        assert candidates[0].source_column == "user_id"
        assert candidates[0].target_table == "users"
        assert candidates[0].target_column == "id"
        assert candidates[0].confidence_score > 0
        assert candidates[0].discovery_methods == [RelationshipDiscoveryMethod.NAMING_PATTERN]

    def test_discover_foreign_key_candidates_no_matches(self):
        """测试发现外键候选（无匹配）"""
        tables = [
            TableMetadata(
                table_name="orders",
                table_comment="订单表",
                engine="InnoDB",
                columns=[
                    ColumnMetadata(
                        column_name="user_id",
                        table_name="orders",
                        ordinal_position=1,
                        data_type="bigint",
                        is_nullable="NO",
                        column_default=None,
                        column_comment=None,
                    ),
                ],
            ),
        ]

        # 没有匹配的 target 表，discover 内部不会调用 SQL
        # 但由于方法签名需要 db_name，传空字符串即可
        scanner = MySQLScanner()
        candidates = scanner.discover_foreign_key_candidates("", tables)

        # 没有匹配的 target 表，应该返回空列表
        assert candidates == []

    def test_calculate_match_rate(self):
        """测试计算匹配率"""
        with patch("mysql.connector.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.execute.return_value = mock_cursor
            # 第一次 fetchone: (100,), 第二次 fetchone: (95,)
            mock_cursor.fetchone.side_effect = [(100,), (95,)]
            mock_connect.return_value = mock_conn

            rel = Relationship(
                source_table="orders",
                source_column="user_id",
                target_table="users",
                target_column="id",
                relationship_type="many-to-one",
                match_rate=0.0,
                verified=False,
            )

            scanner = MySQLScanner()
            with scanner:
                match_rate = scanner.calculate_match_rate("test_db", rel)

            assert match_rate == 0.95

    def test_calculate_match_rate_zero_total(self):
        """测试计算匹配率（总数为 0）"""
        with patch("mysql.connector.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.execute.return_value = mock_cursor
            # 第一次 fetchone: (0,), 直接返回 0
            mock_cursor.fetchone.side_effect = [(0,)]
            mock_connect.return_value = mock_conn

            rel = Relationship(
                source_table="orders",
                source_column="user_id",
                target_table="users",
                target_column="id",
                relationship_type="many-to-one",
                match_rate=0.0,
                verified=False,
            )

            scanner = MySQLScanner()
            with scanner:
                match_rate = scanner.calculate_match_rate("test_db", rel)

            # 总数为 0 时应该返回 0
            assert match_rate == 0.0

    def test_connection_error_handling(self):
        """测试连接错误处理"""
        with patch("mysql.connector.connect", side_effect=MySQLError("Connection refused")):
            scanner = MySQLScanner()

            with pytest.raises(MySQLError):
                # 触发连接建立
                scanner._get_connection("test_db")

    def test_singular_plural_table_matching(self):
        """测试单复数表名匹配"""
        tables = [
            TableMetadata(
                table_name="order_items",
                table_comment="订单项表",
                engine="InnoDB",
                columns=[
                    ColumnMetadata(
                        column_name="order_id",
                        table_name="order_items",
                        ordinal_position=1,
                        data_type="bigint",
                        is_nullable="NO",
                        column_default=None,
                        column_comment=None,
                    ),
                ],
            ),
            TableMetadata(
                table_name="orders",
                table_comment="订单表",
                engine="InnoDB",
                columns=[
                    ColumnMetadata(
                        column_name="id",
                        table_name="orders",
                        ordinal_position=1,
                        data_type="bigint",
                        is_nullable="NO",
                        column_default=None,
                        column_comment=None,
                    ),
                ],
            ),
        ]

        with patch("mysql.connector.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.execute.return_value = mock_cursor
            mock_cursor.fetchone.side_effect = [
                (100,), (95,),   # match_rate
                (100,), (200,), (95,),  # value_overlap
            ]
            mock_connect.return_value = mock_conn

            scanner = MySQLScanner()
            candidates = scanner.discover_foreign_key_candidates("test_db", tables)

        assert len(candidates) == 1
        assert candidates[0].source_table == "order_items"
        assert candidates[0].source_column == "order_id"
        assert candidates[0].target_table == "orders"


class TestTypeCompatibility:
    """数据类型兼容性测试"""

    def test_identical_types(self):
        compat = MySQLScanner._check_type_compatibility("INT", "INT")
        assert compat.compatible
        assert compat.base_types == ("int", "int")
        assert not compat.convertible

    def test_compatible_numeric_types(self):
        compat = MySQLScanner._check_type_compatibility("BIGINT", "SMALLINT")
        assert compat.compatible
        assert compat.convertible is False

    def test_compatible_string_types(self):
        compat = MySQLScanner._check_type_compatibility("VARCHAR(255)", "TEXT")
        assert compat.compatible
        assert compat.base_types == ("varchar", "text")

    def test_convertible_numeric_float(self):
        compat = MySQLScanner._check_type_compatibility("INT", "FLOAT")
        assert compat.compatible
        assert compat.convertible

    def test_incompatible_types(self):
        compat = MySQLScanner._check_type_compatibility("INT", "VARCHAR(255)")
        assert not compat.compatible
        assert not compat.convertible

    def test_null_input(self):
        compat = MySQLScanner._check_type_compatibility("", "INT")
        assert not compat.compatible
        assert compat.base_types == ("", "")
        assert not compat.convertible

    def test_compatible_date_types(self):
        compat = MySQLScanner._check_type_compatibility("DATETIME", "TIMESTAMP")
        assert compat.compatible

    def test_compatible_blob_types(self):
        compat = MySQLScanner._check_type_compatibility("BLOB", "TINYBLOB")
        assert compat.compatible

    def test_float_group(self):
        compat = MySQLScanner._check_type_compatibility("DECIMAL", "DOUBLE")
        assert compat.compatible


class TestValueOverlap:
    """值分布重叠度测试"""

    def test_calculate_value_overlap(self):
        with patch("mysql.connector.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.side_effect = [
                (100,),   # src distinct
                (200,),   # tgt distinct
                (80,),    # intersection
            ]
            mock_connect.return_value = mock_conn

            rel = Relationship(
                source_table="orders",
                source_column="user_id",
                target_table="users",
                target_column="id",
                relationship_type="many-to-one",
            )

            scanner = MySQLScanner()
            with scanner:
                overlap_rate, jaccard = scanner.calculate_value_overlap("test_db", rel)

        assert overlap_rate == 0.8  # 80/100
        assert jaccard == pytest.approx(0.3636, rel=1e-3)  # 80/(100+200-80) = 80/220

    def test_value_overlap_zero_src(self):
        with patch("mysql.connector.connect") as mock_connect:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.side_effect = [(0,), (0,), (0,)]
            mock_connect.return_value = mock_conn

            rel = Relationship(
                source_table="orders",
                source_column="user_id",
                target_table="users",
                target_column="id",
                relationship_type="many-to-one",
            )

            scanner = MySQLScanner()
            with scanner:
                overlap_rate, jaccard = scanner.calculate_value_overlap("test_db", rel)

        assert overlap_rate == 0.0
        assert jaccard == 0.0


class TestConfidenceScore:
    """置信度评分测试"""

    def test_high_confidence(self):
        compat = MySQLScanner.TypeCompatibility(compatible=True, base_types=("int", "int"), convertible=False)
        rel = Relationship(
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
            relationship_type="many-to-one",
            discovery_methods=[RelationshipDiscoveryMethod.NAMING_PATTERN],
        )

        score = MySQLScanner.calculate_confidence_score(rel, 0.9, compat, 0.95)
        # 0.2*1.0 + 0.3*0.9 + 0.25*1.0 + 0.25*0.95 = 0.2 + 0.27 + 0.25 + 0.2375 = 0.9575
        assert score == pytest.approx(0.9575, rel=1e-3)

    def test_low_confidence(self):
        compat = MySQLScanner.TypeCompatibility(compatible=False, base_types=("int", "varchar"), convertible=False)
        rel = Relationship(
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
            relationship_type="many-to-one",
            discovery_methods=[],
        )

        score = MySQLScanner.calculate_confidence_score(rel, 0.1, compat, 0.2)
        # 0.2*0 + 0.3*0.1 + 0.25*0 + 0.25*0.2 = 0 + 0.03 + 0 + 0.05 = 0.08
        assert score == pytest.approx(0.08, rel=1e-3)

    def test_convertible_type_score(self):
        compat = MySQLScanner.TypeCompatibility(compatible=True, base_types=("int", "float"), convertible=True)
        rel = Relationship(
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
            relationship_type="many-to-one",
            discovery_methods=[RelationshipDiscoveryMethod.NAMING_PATTERN],
        )

        score = MySQLScanner.calculate_confidence_score(rel, 0.8, compat, 0.8)
        # 0.2*1.0 + 0.3*0.8 + 0.25*0.6 + 0.25*0.8 = 0.2 + 0.24 + 0.15 + 0.2 = 0.79
        assert score == pytest.approx(0.79, rel=1e-3)

    def test_confidence_capped_at_1(self):
        compat = MySQLScanner.TypeCompatibility(compatible=True, base_types=("int", "int"), convertible=False)
        rel = Relationship(
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
            relationship_type="many-to-one",
            discovery_methods=[RelationshipDiscoveryMethod.NAMING_PATTERN],
        )

        score = MySQLScanner.calculate_confidence_score(rel, 1.0, compat, 1.0)
        assert score == 1.0
