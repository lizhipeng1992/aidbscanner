"""MySQL database metadata scanner"""
import logging
import re
from typing import Any, Dict, List, Optional, Set

import mysql.connector
from mysql.connector import Error

from .base_scanner import BaseDatabaseScanner
from .models import TableMetadata, ColumnMetadata, Relationship, RelationshipDiscoveryMethod
from config.settings import settings

logger = logging.getLogger(__name__)


class MySQLScanner(BaseDatabaseScanner):
    """MySQL database metadata scanner"""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        super().__init__(host=host, port=port, user=user, password=password)

    def _is_connected(self) -> bool:
        return self._connection is not None and self._connection.is_connected()

    def _get_connection(self, database: str):
        """Get database connection"""
        if not self._is_connected():
            try:
                self._connection = mysql.connector.connect(
                    host=self.host or settings.db_host,
                    port=self.port or settings.db_port,
                    user=self.user or settings.db_user,
                    password=self.password or settings.db_password,
                    database=database,
                    autocommit=True,
                )
            except Error as e:
                logger.error(f"Failed to connect to MySQL: {e}")
                raise
        return self._connection

    def list_databases(self) -> List[str]:
        """List all databases"""
        conn = mysql.connector.connect(
            host=self.host or settings.db_host,
            port=self.port or settings.db_port,
            user=self.user or settings.db_user,
            password=self.password or settings.db_password,
        )
        try:
            cursor = conn.cursor()
            cursor.execute("SHOW DATABASES")
            databases = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return databases
        finally:
            conn.close()

    def get_primary_keys(self, cursor, table_name: str, db_name: str) -> Set[str]:
        """Get primary key column names for a table."""
        cursor.execute(
            f"""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = '{db_name}'
            AND TABLE_NAME = '{table_name}'
            AND INDEX_NAME = 'PRIMARY'
        """
        )
        return {row["COLUMN_NAME"] for row in cursor.fetchall()}

    def get_auto_increment_columns(self, cursor, table_name: str, db_name: str) -> Set[str]:
        """Get auto-increment column names for a table."""
        cursor.execute(
            f"""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = '{db_name}'
            AND TABLE_NAME = '{table_name}'
            AND EXTRA LIKE '%auto_increment%'
        """
        )
        return {row["COLUMN_NAME"] for row in cursor.fetchall()}

    def _get_columns_metadata(self, cursor, table_name: str, db_name: str) -> List[ColumnMetadata]:
        """Get metadata for all columns in a table."""
        cursor.execute(f"SHOW FULL COLUMNS FROM `{table_name}`")
        columns_info = cursor.fetchall()

        primary_keys = self.get_primary_keys(cursor, table_name, db_name)
        auto_increment_cols = self.get_auto_increment_columns(cursor, table_name, db_name)

        columns = []
        for col_info in columns_info:
            col = ColumnMetadata(
                column_name=col_info["Field"],
                table_name=table_name,
                data_type=col_info["Type"],
                character_maximum_length=self._get_char_length(col_info["Type"]),
                is_nullable=col_info["Null"],
                column_default=col_info.get("Default"),
                column_comment=col_info.get("Comment"),
                is_primary_key=col_info["Field"] in primary_keys,
                is_auto_increment=col_info["Field"] in auto_increment_cols,
                ordinal_position=int(col_info["Key"]) if col_info.get("Key") and str(col_info["Key"]).isdigit() else 0,
            )
            columns.append(col)

        columns.sort(key=lambda x: x.ordinal_position)
        return columns

    @staticmethod
    def is_data_type_compatible(type1: str, type2: str) -> bool:
        """Check if two MySQL data types are compatible."""
        if not type1 or not type2:
            return False

        base1 = type1.strip().lower().split("(")[0].split("[")[0]
        base2 = type2.strip().lower().split("(")[0].split("[")[0]

        if base1 == base2:
            return True

        numeric_groups = [
            {"tinyint", "smallint", "mediumint", "int", "bigint"},
        ]

        for group in numeric_groups:
            if base1 in group and base2 in group:
                return True

        string_groups = [
            {"char", "varchar", "text", "tinytext", "mediumtext", "longtext"},
        ]

        for group in string_groups:
            if base1 in group and base2 in group:
                return True

        return False

    def _quote_identifier(self, name: str) -> str:
        """Quote a MySQL identifier with backticks."""
        return f"`{name}`"

    def _query_table_info(self, cursor, table_name: str, db_name: str) -> Optional[Dict[str, Any]]:
        """Query table metadata."""
        cursor.execute(f"SHOW TABLE STATUS LIKE '{table_name}'")
        return cursor.fetchone()

    def _list_tables_query(self, db_name: str) -> str:
        return "SHOW TABLES"

    def _extract_table_names(self, rows, db_name: str) -> List[str]:
        return [row[f"Tables_in_{db_name}"] for row in rows]

    def _build_sample_query(self, table_name: str, column_name: str) -> str:
        return (
            f"SELECT `{column_name}` "
            f"FROM `{table_name}` "
            f"WHERE `{column_name}` IS NOT NULL "
            f"LIMIT %s"
        )

    def _get_char_length(self, data_type: str) -> Optional[int]:
        """Extract character length from data type string."""
        match = re.search(r"\((\d+)\)", data_type)
        if match:
            return int(match.group(1))
        return None
