"""MySQL database metadata scanner"""
import logging
from typing import List, Optional, Any, Dict
import mysql.connector
from mysql.connector import Error

from .models import TableMetadata, ColumnMetadata, Relationship, RelationshipDiscoveryMethod
from config.settings import settings

logger = logging.getLogger(__name__)


class MySQLScanner:
    """MySQL database metadata scanner"""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """Initialize scanner.

        Args:
            host: MySQL host address
            port: MySQL port
            user: Username
            password: Password
        """
        self.host = host or settings.mysql_host
        self.port = port or settings.mysql_port
        self.user = user or settings.mysql_user
        self.password = password or settings.mysql_password
        self._connection = None

    def _get_connection(self, database: str):
        """Get database connection"""
        if self._connection is None or not self._connection.is_connected():
            try:
                self._connection = mysql.connector.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=database,
                    autocommit=True,
                )
            except Error as e:
                logger.error(f"Failed to connect to MySQL: {e}")
                raise
        return self._connection

    def close(self):
        """Close connection"""
        if self._connection and self._connection.is_connected():
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def list_databases(self) -> List[str]:
        """List all databases"""
        # Connect without specifying a database parameter
        conn = mysql.connector.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
        )
        try:
            cursor = conn.cursor()
            cursor.execute("SHOW DATABASES")
            databases = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return databases
        finally:
            conn.close()

    @staticmethod
    def _is_data_type_compatible(type1: str, type2: str) -> bool:
        """Check if two MySQL data types are compatible (for foreign key relationships).

        Args:
            type1: First column data type
            type2: Second column data type

        Returns:
            Whether compatible
        """
        if not type1 or not type2:
            return False

        # Normalize type: remove length, precision, etc.
        base1 = type1.strip().lower().split("(")[0].split("[")[0]
        base2 = type2.strip().lower().split("(")[0].split("[")[0]

        # Exact match
        if base1 == base2:
            return True

        # Numeric type compatibility groups
        numeric_groups = [
            {"tinyint", "smallint", "mediumint", "int", "bigint"},
        ]

        for group in numeric_groups:
            if base1 in group and base2 in group:
                return True

        # String type compatibility groups
        string_groups = [
            {"char", "varchar", "text", "tinytext", "mediumtext", "longtext"},
        ]

        for group in string_groups:
            if base1 in group and base2 in group:
                return True

        return False

    def scan_database(self, db_name: str) -> List[TableMetadata]:
        """Scan all table structures in the specified database.

        Args:
            db_name: Database name

        Returns:
            Table metadata list
        """
        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor(dictionary=True)

            # Get all tables
            cursor.execute("SHOW TABLES")
            tables = [row[f"Tables_in_{db_name}"] for row in cursor.fetchall()]

            result = []
            for table_name in tables:
                table_meta = self._get_table_metadata(cursor, table_name, db_name)
                result.append(table_meta)

            cursor.close()
            logger.info(f"Scan complete: database {db_name} has {len(result)} tables")
            return result

        except Error as e:
            logger.error(f"Failed to scan database {db_name}: {e}")
            return []

    def scan_table_only(
        self, db_name: str, table_name: str
    ) -> Optional[TableMetadata]:
        """Scan metadata for a single table (without scanning the full database).

        Args:
            db_name: Database name
            table_name: Table name

        Returns:
            Table metadata, or None if the table does not exist
        """
        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor(dictionary=True)

            table_meta = self._get_table_metadata(cursor, table_name, db_name)
            cursor.close()

            if not table_meta.columns:
                logger.warning(f"Table {db_name}.{table_name} does not exist or has no columns")
                return None

            return table_meta

        except Error as e:
            logger.error(f"Failed to scan table {db_name}.{table_name}: {e}")
            return None

    def get_sample_data_batch(
        self, db_name: str, table_name: str, column_names: List[str], limit: int = 5
    ) -> Dict[str, List[Any]]:
        """Batch fetch sample data for multiple columns in a single query.

        Args:
            db_name: Database name
            table_name: Table name
            column_names: Column name list
            limit: Number of sample rows per column

        Returns:
            {column_name: [sample_values]} dictionary
        """
        if not column_names:
            return {}

        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor()

            # Single query to get sample data for all columns
            cols = ", ".join(f"`{c}`" for c in column_names)
            query = f"SELECT {cols} FROM `{table_name}` WHERE {f' AND '.join(f'`{c}` IS NOT NULL' for c in column_names)} LIMIT %s"
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()

            cursor.close()

            # Organize results by column
            result: Dict[str, List[Any]] = {col: [] for col in column_names}
            seen: Dict[str, set] = {col: set() for col in column_names}

            for row in rows:
                for i, col in enumerate(column_names):
                    val = row[i]
                    if val is not None:
                        val_str = str(val)
                        if val_str not in seen[col]:
                            seen[col].add(val_str)
                            result[col].append(val)
                            if len(result[col]) >= limit:
                                result[col].sort(key=lambda x: str(x))
                                break

            return result

        except Error as e:
            logger.error(f"Failed to batch fetch sample data: {e}")
            return {col: [] for col in column_names}

    def _get_table_metadata(
        self, cursor, table_name: str, db_name: str
    ) -> TableMetadata:
        """Get metadata for a single table."""
        # Get table info
        cursor.execute(f"SHOW TABLE STATUS LIKE '{table_name}'")
        table_info = cursor.fetchone()

        table_meta = TableMetadata(
            table_name=table_name,
            table_comment=table_info.get("Comment") if table_info else None,
            engine=table_info.get("Engine", "InnoDB") if table_info else "InnoDB",
        )

        # Get column info
        columns = self._get_columns_metadata(cursor, table_name, db_name)
        table_meta.columns = columns

        return table_meta

    def _get_columns_metadata(
        self, cursor, table_name: str, db_name: str
    ) -> List[ColumnMetadata]:
        """Get metadata for all columns in a table."""
        cursor.execute(f"SHOW FULL COLUMNS FROM `{table_name}`")
        columns_info = cursor.fetchall()

        # Get primary key info
        cursor.execute(
            f"""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = '{db_name}'
            AND TABLE_NAME = '{table_name}'
            AND INDEX_NAME = 'PRIMARY'
        """
        )
        primary_keys = {row["COLUMN_NAME"] for row in cursor.fetchall()}

        # Get auto-increment columns (from COLUMNS table, EXTRA column)
        cursor.execute(
            f"""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = '{db_name}'
            AND TABLE_NAME = '{table_name}'
            AND EXTRA LIKE '%auto_increment%'
        """
        )
        auto_increment_cols = {row["COLUMN_NAME"] for row in cursor.fetchall()}

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
                ordinal_position=int(col_info["Key"]) if col_info["Key"].isdigit() else 0,
            )
            # Fix ordinal_position
            col.ordinal_position = int(col_info["Key"]) if col_info.get("Key") and str(col_info["Key"]).isdigit() else 0
            columns.append(col)

        # Sort by ordinal_position
        columns.sort(key=lambda x: x.ordinal_position)

        return columns

    def _get_char_length(self, data_type: str) -> Optional[int]:
        """Extract character length from data type string."""
        import re

        # Match VARCHAR(n), CHAR(n), etc.
        match = re.search(r"\((\d+)\)", data_type)
        if match:
            return int(match.group(1))
        return None

    def get_sample_data(
        self, db_name: str, table_name: str, column_name: str, limit: int = 5
    ) -> List[Any]:
        """Get sample data for a column.

        Args:
            db_name: Database name
            table_name: Table name
            column_name: Column name
            limit: Number of rows to return

        Returns:
            Sample data list
        """
        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor()

            # Use parameterized queries to prevent SQL injection
            query = f"""
                SELECT `{column_name}`
                FROM `{table_name}`
                WHERE `{column_name}` IS NOT NULL
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            results = cursor.fetchall()

            # Extract non-null values and deduplicate
            sample_values = []
            for row in results:
                if row[0] is not None and str(row[0]) not in [str(v) for v in sample_values]:
                    sample_values.append(row[0])
                    if len(sample_values) >= limit:
                        break

            cursor.close()
            return sample_values

        except Error as e:
            logger.error(f"Failed to fetch sample data: {e}")
            return []

    def discover_foreign_key_candidates(
        self, tables: List[TableMetadata]
    ) -> List[Relationship]:
        """Discover potential foreign keys based on naming conventions.

        Args:
            tables: Table metadata list

        Returns:
            Potential foreign key relationships list
        """
        candidates = []

        # Build column index
        table_columns = {}
        for table in tables:
            table_columns[table.table_name] = {col.column_name: col for col in table.columns}

        # Find columns ending with _id
        for table in tables:
            for col in table.columns:
                if col.column_name.endswith("_id"):
                    # Try to find the corresponding table
                    base_name = col.column_name[:-3]  # Strip _id suffix

                    # Possible target table names (singular/plural forms)
                    possible_targets = [base_name, f"{base_name}s", f"{base_name}es"]

                    for target_table_name in possible_targets:
                        if target_table_name in table_columns and target_table_name != table.table_name:
                            # Simplified: assume target table primary key is table_name_id or id
                            possible_pk = [target_table_name + "_id", "id"]

                            for pk in possible_pk:
                                if pk in table_columns[target_table_name]:
                                    target_col = table_columns[target_table_name][pk]

                                    # Check if data types are compatible
                                    type_compatible = self._is_data_type_compatible(col.data_type, target_col.data_type)

                                    rel = Relationship(
                                        source_table=table.table_name,
                                        source_column=col.column_name,
                                        target_table=target_table_name,
                                        target_column=pk,
                                        relationship_type="many-to-one",
                                        match_rate=0.0,
                                        confidence_score=0.7 if type_compatible else 0.5,  # Naming pattern base score
                                        verified=False,
                                        discovery_methods=[RelationshipDiscoveryMethod.NAMING_PATTERN],
                                        data_type_match=type_compatible,
                                    )
                                    candidates.append(rel)
                                    break
                            break

        return candidates

    def calculate_match_rate(
        self, db_name: str, rel: Relationship
    ) -> float:
        """Calculate foreign key match rate.

        Args:
            db_name: Database name
            rel: Relationship object

        Returns:
            Match rate (0-1)
        """
        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor()

            # Get source column distinct values count
            cursor.execute(
                f"""
                SELECT COUNT(DISTINCT `{rel.source_column}`) as src_count
                FROM `{rel.source_table}`
            """
            )
            src_count = cursor.fetchone()[0]

            if src_count == 0:
                return 0.0

            # Get count of matching values
            cursor.execute(
                f"""
                SELECT COUNT(DISTINCT s.`{rel.source_column}`) as match_count
                FROM `{rel.source_table}` s
                INNER JOIN `{rel.target_table}` t
                ON s.`{rel.source_column}` = t.`{rel.target_column}`
            """
            )
            match_count = cursor.fetchone()[0]

            cursor.close()

            return match_count / src_count if src_count > 0 else 0.0

        except Error as e:
            logger.error(f"Failed to calculate match rate: {e}")
            return 0.0
