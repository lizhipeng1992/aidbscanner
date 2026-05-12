"""SQL Server database metadata scanner"""
import logging
from typing import Any, Dict, List, Optional, Set

from .base_scanner import BaseDatabaseScanner
from .models import ColumnMetadata

logger = logging.getLogger(__name__)


class SQLServerScanner(BaseDatabaseScanner):
    """SQL Server database metadata scanner.

    Uses pymssql for connectivity.
    Default port: 1433
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        super().__init__(host=host, port=port, user=user, password=password)

    def _is_connected(self) -> bool:
        return self._connection is not None

    def _get_connection(self, database: str):
        """Get database connection using pymssql."""
        if not self._is_connected():
            try:
                import pymssql
            except ImportError as e:
                logger.error(f"pymssql is required for SQL Server: {e}")
                raise
            try:
                self._connection = pymssql.connect(
                    server=f"{self.host or 'localhost'}:{self.port or 1433}",
                    user=self.user or "sa",
                    password=self.password or "",
                    database=database,
                )
            except pymssql.OperationalError as e:
                logger.error(f"Failed to connect to SQL Server: {e}")
                raise
        return self._connection

    def list_databases(self) -> List[str]:
        """List all databases on the server."""
        import pymssql
        conn = pymssql.connect(
            server=f"{self.host or 'localhost'}:{self.port or 1433}",
            user=self.user or "sa",
            password=self.password or "",
        )
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sys.databases WHERE name NOT IN ('master', 'tempdb', 'model', 'msdb')")
            databases = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return databases
        finally:
            conn.close()

    def get_primary_keys(self, cursor, table_name: str, db_name: str) -> Set[str]:
        """Get primary key column names for a table."""
        cursor.execute(
            f"""
            SELECT kcu.COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
            INNER JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                AND kcu.TABLE_SCHEMA = tc.TABLE_SCHEMA
                AND kcu.TABLE_NAME = tc.TABLE_NAME
            WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
            AND kcu.TABLE_NAME = '{table_name}'
            """
        )
        return {row[0] for row in cursor.fetchall()}

    def get_auto_increment_columns(self, cursor, table_name: str, db_name: str) -> Set[str]:
        """Get identity/auto-increment column names for a table."""
        cursor.execute(
            f"""
            SELECT c.COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS c
            WHERE c.TABLE_NAME = '{table_name}'
            AND c.IS_IDENTITY = 'YES'
            """
        )
        return {row[0] for row in cursor.fetchall()}

    def _get_columns_metadata(self, cursor, table_name: str, db_name: str) -> List[ColumnMetadata]:
        """Get metadata for all columns in a table."""
        cursor.execute(
            f"""
            SELECT c.COLUMN_NAME,
                   c.DATA_TYPE,
                   c.CHARACTER_MAXIMUM_LENGTH AS character_maximum_length,
                   c.IS_NULLABLE AS is_nullable,
                   c.COLUMN_DEFAULT AS column_default,
                   c.ORDINAL_POSITION AS ordinal_position,
                   ep.value AS column_comment
            FROM INFORMATION_SCHEMA.COLUMNS c
            LEFT JOIN sys.extended_properties ep
                ON ep.major_id = OBJECT_ID('{db_name}.dbo.{table_name}')
                AND ep.minor_id = c.ORDINAL_POSITION
                AND ep.name = 'MS_Description'
            WHERE c.TABLE_NAME = '{table_name}'
            ORDER BY c.ORDINAL_POSITION
            """
        )
        rows = cursor.fetchall()

        primary_keys = self.get_primary_keys(cursor, table_name, db_name)
        auto_increment_cols = self.get_auto_increment_columns(cursor, table_name, db_name)

        columns = []
        for row in rows:
            is_nullable = (row[3] or "YES") == "YES"
            col = ColumnMetadata(
                column_name=row[0],
                table_name=table_name,
                data_type=row[1],
                character_maximum_length=row[2] if row[2] and row[2] > 0 else None,
                is_nullable=is_nullable,
                column_default=row[4],
                column_comment=row[5],
                is_primary_key=row[0] in primary_keys,
                is_auto_increment=row[0] in auto_increment_cols,
                ordinal_position=row[6] if row[6] else 0,
            )
            columns.append(col)

        columns.sort(key=lambda x: x.ordinal_position)
        return columns

    @staticmethod
    def is_data_type_compatible(type1: str, type2: str) -> bool:
        """Check if two SQL Server data types are compatible."""
        if not type1 or not type2:
            return False

        base1 = type1.strip().lower().split("(")[0].split("[")[0]
        base2 = type2.strip().lower().split("(")[0].split("[")[0]

        if base1 == base2:
            return True

        numeric_groups = [
            {"tinyint", "smallint", "int", "bigint"},
            {"decimal", "numeric", "float", "real", "money", "smallmoney"},
        ]

        for group in numeric_groups:
            if base1 in group and base2 in group:
                return True

        string_groups = [
            {"char", "varchar", "nchar", "nvarchar", "text", "ntext"},
        ]

        for group in string_groups:
            if base1 in group and base2 in group:
                return True

        return False

    def _quote_identifier(self, name: str) -> str:
        """Quote a SQL Server identifier with square brackets."""
        return f"[{name}]"

    def _query_table_info(self, cursor, table_name: str, db_name: str) -> Optional[Dict[str, Any]]:
        """Query table metadata."""
        cursor.execute(
            f"""
            SELECT t.name AS Name,
                   p.rows AS RowCounts
            FROM sys.tables t
            INNER JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id IN (0, 1)
            WHERE t.name = '{table_name}'
            """
        )
        row = cursor.fetchone()
        if row:
            return {
                "Name": row[0],
                "Engine": "",
                "Comment": None,
            }
        return None

    def _list_tables_query(self, db_name: str) -> str:
        return "SELECT name FROM sys.tables WHERE is_ms_shipped = 0"

    def _extract_table_names(self, rows, db_name: str) -> List[str]:
        return [row[0] for row in rows]

    def _build_sample_query(self, table_name: str, column_name: str) -> str:
        return (
            f"SELECT TOP ? [{column_name}] "
            f"FROM [{table_name}] "
            f"WHERE [{column_name}] IS NOT NULL"
        )
