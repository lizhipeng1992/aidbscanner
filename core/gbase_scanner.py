"""GBase 8s database metadata scanner"""
import logging
from typing import Any, Dict, List, Optional, Set

from .base_scanner import BaseDatabaseScanner
from .models import ColumnMetadata

logger = logging.getLogger(__name__)


class GBaseScanner(BaseDatabaseScanner):
    """GBase 8s database metadata scanner.

    GBase 8s is based on Informix technology and uses ODBC for connectivity.
    Default port: 8888
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
        """Get database connection using ODBC."""
        if not self._is_connected():
            try:
                import pyodbc
            except ImportError as e:
                logger.error(f"pyodbc is required for GBase 8s: {e}")
                raise
            try:
                conn_str = (
                    f"DRIVER={{GBase 8s Client-SDK}};"
                    f"SERVER={self.host or 'localhost'};"
                    f"PORT={self.port or 8888};"
                    f"DATABASE={database};"
                    f"UID={self.user or 'gbasedb'};"
                    f"PWD={self.password or ''};"
                )
                self._connection = pyodbc.connect(conn_str)
            except pyodbc.Error as e:
                logger.error(f"Failed to connect to GBase 8s: {e}")
                raise
        return self._connection

    def list_databases(self) -> List[str]:
        """List all databases on the server."""
        import pyodbc
        conn = pyodbc.connect(
            f"DRIVER={{GBase 8s Client-SDK}};"
            f"SERVER={self.host or 'localhost'};"
            f"PORT={self.port or 8888};"
            f"UID={self.user or 'gbasedb'};"
            f"PWD={self.password or ''};"
        )
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT datname FROM sysdatabases WHERE datname NOT IN ('sysmaster', 'sysutils', 'sysuser', 'syssysinfo', 'informix')")
            databases = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return databases
        finally:
            conn.close()

    def get_primary_keys(self, cursor, table_name: str, db_name: str) -> Set[str]:
        """Get primary key column names for a table."""
        cursor.execute(
            f"""
            SELECT c.colname
            FROM systables t
            JOIN syscolumns c ON t.tabid = c.tabid
            WHERE t.tabname = '{table_name}'
            AND (c.colstat & 1) = 1
            """
        )
        return {row[0] for row in cursor.fetchall()}

    def get_auto_increment_columns(self, cursor, table_name: str, db_name: str) -> Set[str]:
        """Get serial/auto-increment column names for a table."""
        cursor.execute(
            f"""
            SELECT c.colname
            FROM systables t
            JOIN syscolumns c ON t.tabid = c.tabid
            WHERE t.tabname = '{table_name}'
            AND c.identity = 1
            """
        )
        return {row[0] for row in cursor.fetchall()}

    def _get_columns_metadata(self, cursor, table_name: str, db_name: str) -> List[ColumnMetadata]:
        """Get metadata for all columns in a table."""
        cursor.execute(
            f"""
            SELECT c.colname AS column_name,
                   c.collength AS character_maximum_length,
                   c.is_nullable AS is_nullable,
                   c.column_default AS column_default,
                   c.collabel AS column_comment,
                   c.colorder AS ordinal_position,
                   t.type_name AS data_type
            FROM systables t
            JOIN syscolumns c ON t.tabid = c.tabid
            WHERE t.tabname = '{table_name}'
            ORDER BY c.colorder
            """
        )
        rows = cursor.fetchall()

        primary_keys = self.get_primary_keys(cursor, table_name, db_name)
        auto_increment_cols = self.get_auto_increment_columns(cursor, table_name, db_name)

        columns = []
        for row in rows:
            col = ColumnMetadata(
                column_name=row[0],
                table_name=table_name,
                data_type=row[6],
                character_maximum_length=row[1] if row[1] and row[1] > 256 else None,
                is_nullable=bool(row[2]) if row[2] is not None else True,
                column_default=row[3],
                column_comment=row[4],
                is_primary_key=row[0] in primary_keys,
                is_auto_increment=row[0] in auto_increment_cols,
                ordinal_position=row[5] if row[5] else 0,
            )
            columns.append(col)

        columns.sort(key=lambda x: x.ordinal_position)
        return columns

    @staticmethod
    def is_data_type_compatible(type1: str, type2: str) -> bool:
        """Check if two GBase data types are compatible."""
        if not type1 or not type2:
            return False

        base1 = type1.strip().lower().split("(")[0].split("[")[0]
        base2 = type2.strip().lower().split("(")[0].split("[")[0]

        if base1 == base2:
            return True

        numeric_groups = [
            {"smallint", "integer", "bigint", "int", "serial", "serial8"},
            {"decimal", "numeric", "float", "real", "double"},
        ]

        for group in numeric_groups:
            if base1 in group and base2 in group:
                return True

        string_groups = [
            {"char", "varchar", "text", "byte", "blob"},
        ]

        for group in string_groups:
            if base1 in group and base2 in group:
                return True

        return False

    def _quote_identifier(self, name: str) -> str:
        """Quote a GBase identifier with double quotes."""
        return f'"{name}"'

    def _query_table_info(self, cursor, table_name: str, db_name: str) -> Optional[Dict[str, Any]]:
        """Query table metadata."""
        cursor.execute(
            f"""
            SELECT tabname AS Name,
                   tabtype AS Type,
                   owner AS Owner
            FROM systables
            WHERE tabname = '{table_name}'
            """
        )
        row = cursor.fetchone()
        if row:
            return {
                "Name": row[0],
                "Type": row[1],
                "Owner": row[2],
                "Comment": None,
                "Engine": "GBase",
            }
        return None

    def _list_tables_query(self, db_name: str) -> str:
        return "SELECT tabname FROM systables WHERE tabid > 99 AND owner != 'informix'"

    def _extract_table_names(self, rows, db_name: str) -> List[str]:
        return [row[0] for row in rows]

    def _build_sample_query(self, table_name: str, column_name: str) -> str:
        return (
            f'SELECT "{column_name}" '
            f'FROM "{table_name}" '
            f'WHERE "{column_name}" IS NOT NULL '
            f"LIMIT ?"
        )
