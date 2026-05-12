"""Abstract base class for database metadata scanners"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set
from .models import TableMetadata, ColumnMetadata, Relationship, RelationshipDiscoveryMethod

logger = logging.getLogger(__name__)


class BaseDatabaseScanner(ABC):
    """Abstract base class for database metadata scanners.

    Subclasses must implement database-specific methods for connecting,
    querying metadata, and type compatibility checking.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self._connection = None

    @abstractmethod
    def _get_connection(self, database: str):
        """Get database connection for the specified database."""
        ...

    @abstractmethod
    def list_databases(self) -> List[str]:
        """List all databases on the server."""
        ...

    @abstractmethod
    def get_primary_keys(self, cursor, table_name: str, db_name: str) -> Set[str]:
        """Get primary key column names for a table."""
        ...

    @abstractmethod
    def get_auto_increment_columns(self, cursor, table_name: str, db_name: str) -> Set[str]:
        """Get auto-increment/identity column names for a table."""
        ...

    @abstractmethod
    def _get_columns_metadata(self, cursor, table_name: str, db_name: str) -> List[ColumnMetadata]:
        """Get metadata for all columns in a table."""
        ...

    @staticmethod
    @abstractmethod
    def is_data_type_compatible(type1: str, type2: str) -> bool:
        """Check if two data types are compatible for foreign key relationships."""
        ...

    def close(self):
        """Close the database connection."""
        if self._connection and self._is_connected():
            self._connection.close()
            self._connection = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @abstractmethod
    def _is_connected(self) -> bool:
        """Check if connection is active."""
        ...

    def scan_database(self, db_name: str) -> List[TableMetadata]:
        """Scan all table structures in the specified database."""
        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor(dictionary=True)

            tables = self._list_tables(cursor, db_name)

            result = []
            for table_name in tables:
                table_meta = self._get_table_metadata(cursor, table_name, db_name)
                result.append(table_meta)

            cursor.close()
            logger.info(f"Scan complete: database {db_name} has {len(result)} tables")
            return result

        except Exception as e:
            logger.error(f"Failed to scan database {db_name}: {e}")
            return []

    def scan_table_only(self, db_name: str, table_name: str) -> Optional[TableMetadata]:
        """Scan metadata for a single table."""
        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor(dictionary=True)

            table_meta = self._get_table_metadata(cursor, table_name, db_name)
            cursor.close()

            if not table_meta.columns:
                logger.warning(f"Table {db_name}.{table_name} does not exist or has no columns")
                return None

            return table_meta

        except Exception as e:
            logger.error(f"Failed to scan table {db_name}.{table_name}: {e}")
            return None

    def get_sample_data(self, db_name: str, table_name: str, column_name: str, limit: int = 5) -> List[Any]:
        """Get sample data for a column."""
        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor()

            query = self._build_sample_query(table_name, column_name)
            cursor.execute(query, (limit,))
            results = cursor.fetchall()

            cursor.close()

            sample_values = []
            for row in results:
                if row[0] is not None and str(row[0]) not in [str(v) for v in sample_values]:
                    sample_values.append(row[0])
                    if len(sample_values) >= limit:
                        break

            return sample_values

        except Exception as e:
            logger.error(f"Failed to fetch sample data: {e}")
            return []

    def get_sample_data_batch(
        self, db_name: str, table_name: str, column_names: List[str], limit: int = 5
    ) -> Dict[str, List[Any]]:
        """Batch fetch sample data for multiple columns in a single query."""
        if not column_names:
            return {}

        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor()

            cols = ", ".join(self._quote_identifier(c) for c in column_names)
            conditions = " AND ".join(
                f"{self._quote_identifier(c)} IS NOT NULL" for c in column_names
            )
            query = f"SELECT {cols} FROM {self._quote_identifier(table_name)} WHERE {conditions} LIMIT %s"
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()

            cursor.close()

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

        except Exception as e:
            logger.error(f"Failed to batch fetch sample data: {e}")
            return {col: [] for col in column_names}

    def discover_foreign_key_candidates(self, tables: List[TableMetadata]) -> List[Relationship]:
        """Discover potential foreign keys based on naming conventions."""
        candidates = []

        table_columns = {}
        for table in tables:
            table_columns[table.table_name] = {col.column_name: col for col in table.columns}

        for table in tables:
            for col in table.columns:
                if col.column_name.endswith("_id"):
                    base_name = col.column_name[:-3]
                    possible_targets = [base_name, f"{base_name}s", f"{base_name}es"]

                    for target_table_name in possible_targets:
                        if target_table_name in table_columns and target_table_name != table.table_name:
                            possible_pk = [target_table_name + "_id", "id"]

                            for pk in possible_pk:
                                if pk in table_columns[target_table_name]:
                                    target_col = table_columns[target_table_name][pk]

                                    type_compatible = self.is_data_type_compatible(
                                        col.data_type, target_col.data_type
                                    )

                                    rel = Relationship(
                                        source_table=table.table_name,
                                        source_column=col.column_name,
                                        target_table=target_table_name,
                                        target_column=pk,
                                        relationship_type="many-to-one",
                                        match_rate=0.0,
                                        confidence_score=0.7 if type_compatible else 0.5,
                                        verified=False,
                                        discovery_methods=[RelationshipDiscoveryMethod.NAMING_PATTERN],
                                        data_type_match=type_compatible,
                                    )
                                    candidates.append(rel)
                                    break
                            break

        return candidates

    def calculate_match_rate(self, db_name: str, rel: Relationship) -> float:
        """Calculate foreign key match rate."""
        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor()

            src_table = self._quote_identifier(rel.source_table)
            src_col = self._quote_identifier(rel.source_column)
            tgt_table = self._quote_identifier(rel.target_table)
            tgt_col = self._quote_identifier(rel.target_column)

            cursor.execute(
                f"SELECT COUNT(DISTINCT {src_col}) as src_count FROM {src_table}"
            )
            src_count = cursor.fetchone()[0]

            if src_count == 0:
                cursor.close()
                return 0.0

            cursor.execute(
                f"SELECT COUNT(DISTINCT s.{src_col}) as match_count "
                f"FROM {src_table} s INNER JOIN {tgt_table} t "
                f"ON s.{src_col} = t.{tgt_col}"
            )
            match_count = cursor.fetchone()[0]

            cursor.close()

            return match_count / src_count if src_count > 0 else 0.0

        except Exception as e:
            logger.error(f"Failed to calculate match rate: {e}")
            return 0.0

    def _get_table_metadata(self, cursor, table_name: str, db_name: str) -> TableMetadata:
        """Get metadata for a single table."""
        table_info = self._query_table_info(cursor, table_name, db_name)

        table_meta = TableMetadata(
            table_name=table_name,
            table_comment=table_info.get("Comment") if table_info else None,
            engine=table_info.get("Engine", "") if table_info else "",
        )

        columns = self._get_columns_metadata(cursor, table_name, db_name)
        table_meta.columns = columns

        return table_meta

    def _list_tables(self, cursor, db_name: str) -> List[str]:
        """List all user tables in the database."""
        cursor.execute(self._list_tables_query(db_name))
        rows = cursor.fetchall()
        return self._extract_table_names(rows, db_name)

    def _quote_identifier(self, name: str) -> str:
        """Quote a SQL identifier (table/column name)."""
        return f'"{name}"'

    @abstractmethod
    def _query_table_info(self, cursor, table_name: str, db_name: str) -> Optional[Dict[str, Any]]:
        """Query table metadata (engine, comment, etc.)."""
        ...

    @abstractmethod
    def _list_tables_query(self, db_name: str) -> str:
        """Return SQL query to list all tables in the database."""
        ...

    @abstractmethod
    def _extract_table_names(self, rows, db_name: str) -> List[str]:
        """Extract table names from query results."""
        ...
