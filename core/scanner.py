"""MySQL 数据库元数据扫描器"""
import logging
from typing import List, Optional, Any, Dict
import mysql.connector
from mysql.connector import Error

from .models import TableMetadata, ColumnMetadata, Relationship, RelationshipDiscoveryMethod
from config.settings import settings

logger = logging.getLogger(__name__)


class MySQLScanner:
    """MySQL 数据库元数据扫描器"""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """初始化扫描器

        Args:
            host: MySQL 主机地址
            port: MySQL 端口
            user: 用户名
            password: 密码
        """
        self.host = host or settings.mysql_host
        self.port = port or settings.mysql_port
        self.user = user or settings.mysql_user
        self.password = password or settings.mysql_password
        self._connection = None

    def _get_connection(self, database: str):
        """获取数据库连接"""
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
                logger.error(f"连接 MySQL 失败：{e}")
                raise
        return self._connection

    def close(self):
        """关闭连接"""
        if self._connection and self._connection.is_connected():
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def list_databases(self) -> List[str]:
        """列出所有数据库"""
        # 先不指定 database 参数连接
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
        """检查两个 MySQL 数据类型是否兼容（可用于外键关联）

        Args:
            type1: 第一个列的数据类型
            type2: 第二个列的数据类型

        Returns:
            是否兼容
        """
        if not type1 or not type2:
            return False

        # 规范化类型：去除长度、精度等修饰
        base1 = type1.strip().lower().split("(")[0].split("[")[0]
        base2 = type2.strip().lower().split("(")[0].split("[")[0]

        # 完全匹配
        if base1 == base2:
            return True

        # 数值类型兼容组
        numeric_groups = [
            {"tinyint", "smallint", "mediumint", "int", "bigint"},
        ]

        for group in numeric_groups:
            if base1 in group and base2 in group:
                return True

        # 字符串类型兼容组
        string_groups = [
            {"char", "varchar", "text", "tinytext", "mediumtext", "longtext"},
        ]

        for group in string_groups:
            if base1 in group and base2 in group:
                return True

        return False

    def scan_database(self, db_name: str) -> List[TableMetadata]:
        """扫描指定数据库的所有表结构

        Args:
            db_name: 数据库名称

        Returns:
            表元数据列表
        """
        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor(dictionary=True)

            # 获取所有表
            cursor.execute("SHOW TABLES")
            tables = [row[f"Tables_in_{db_name}"] for row in cursor.fetchall()]

            result = []
            for table_name in tables:
                table_meta = self._get_table_metadata(cursor, table_name, db_name)
                result.append(table_meta)

            cursor.close()
            logger.info(f"扫描完成：数据库 {db_name} 共 {len(result)} 张表")
            return result

        except Error as e:
            logger.error(f"扫描数据库 {db_name} 失败：{e}")
            return []

    def scan_table_only(
        self, db_name: str, table_name: str
    ) -> Optional[TableMetadata]:
        """仅扫描指定表的元数据（不扫描全库）

        Args:
            db_name: 数据库名
            table_name: 表名

        Returns:
            表元数据，不存在则返回 None
        """
        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor(dictionary=True)

            table_meta = self._get_table_metadata(cursor, table_name, db_name)
            cursor.close()

            if not table_meta.columns:
                logger.warning(f"表 {db_name}.{table_name} 不存在或无字段")
                return None

            return table_meta

        except Error as e:
            logger.error(f"扫描表 {db_name}.{table_name} 失败：{e}")
            return None

    def get_sample_data_batch(
        self, db_name: str, table_name: str, column_names: List[str], limit: int = 5
    ) -> Dict[str, List[Any]]:
        """批量获取多个字段的示例数据（单次查询）

        Args:
            db_name: 数据库名
            table_name: 表名
            column_names: 字段名列表
            limit: 每个字段返回的示例数据条数

        Returns:
            {column_name: [sample_values]} 字典
        """
        if not column_names:
            return {}

        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor()

            # 单次查询获取所有列的示例数据
            cols = ", ".join(f"`{c}`" for c in column_names)
            query = f"SELECT {cols} FROM `{table_name}` WHERE {f' AND '.join(f'`{c}` IS NOT NULL' for c in column_names)} LIMIT %s"
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()

            cursor.close()

            # 按列组织结果
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
            logger.error(f"批量获取示例数据失败：{e}")
            return {col: [] for col in column_names}

    def _get_table_metadata(
        self, cursor, table_name: str, db_name: str
    ) -> TableMetadata:
        """获取单个表的元数据"""
        # 获取表信息
        cursor.execute(f"SHOW TABLE STATUS LIKE '{table_name}'")
        table_info = cursor.fetchone()

        table_meta = TableMetadata(
            table_name=table_name,
            table_comment=table_info.get("Comment") if table_info else None,
            engine=table_info.get("Engine", "InnoDB") if table_info else "InnoDB",
        )

        # 获取字段信息
        columns = self._get_columns_metadata(cursor, table_name, db_name)
        table_meta.columns = columns

        return table_meta

    def _get_columns_metadata(
        self, cursor, table_name: str, db_name: str
    ) -> List[ColumnMetadata]:
        """获取表的所有字段元数据"""
        cursor.execute(f"SHOW FULL COLUMNS FROM `{table_name}`")
        columns_info = cursor.fetchall()

        # 获取主键信息
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

        # 获取自增字段（从 COLUMNS 表查询，EXTRA 字段在 COLUMNS 表中）
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
            # 修正 ordinal_position
            col.ordinal_position = int(col_info["Key"]) if col_info.get("Key") and str(col_info["Key"]).isdigit() else 0
            columns.append(col)

        # 按 ordinal_position 排序
        columns.sort(key=lambda x: x.ordinal_position)

        return columns

    def _get_char_length(self, data_type: str) -> Optional[int]:
        """从数据类型中提取字符长度"""
        import re

        # 匹配 VARCHAR(n), CHAR(n) 等
        match = re.search(r"\((\d+)\)", data_type)
        if match:
            return int(match.group(1))
        return None

    def get_sample_data(
        self, db_name: str, table_name: str, column_name: str, limit: int = 5
    ) -> List[Any]:
        """获取字段的示例数据

        Args:
            db_name: 数据库名
            table_name: 表名
            column_name: 字段名
            limit: 返回条数

        Returns:
            示例数据列表
        """
        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor()

            # 使用参数化查询防止 SQL 注入
            query = f"""
                SELECT `{column_name}`
                FROM `{table_name}`
                WHERE `{column_name}` IS NOT NULL
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            results = cursor.fetchall()

            # 提取非空值并去重
            sample_values = []
            for row in results:
                if row[0] is not None and str(row[0]) not in [str(v) for v in sample_values]:
                    sample_values.append(row[0])
                    if len(sample_values) >= limit:
                        break

            cursor.close()
            return sample_values

        except Error as e:
            logger.error(f"获取示例数据失败：{e}")
            return []

    def discover_foreign_key_candidates(
        self, tables: List[TableMetadata]
    ) -> List[Relationship]:
        """基于命名规则发现潜在的外键关系

        Args:
            tables: 表元数据列表

        Returns:
            潜在外键关系列表
        """
        candidates = []

        # 构建字段索引
        table_columns = {}
        for table in tables:
            table_columns[table.table_name] = {col.column_name: col for col in table.columns}

        # 查找 _id 结尾的字段
        for table in tables:
            for col in table.columns:
                if col.column_name.endswith("_id"):
                    # 尝试找到对应的表
                    base_name = col.column_name[:-3]  # 去掉 _id 后缀

                    # 可能的目标表名（单数/复数形式）
                    possible_targets = [base_name, f"{base_name}s", f"{base_name}es"]

                    for target_table_name in possible_targets:
                        if target_table_name in table_columns and target_table_name != table.table_name:
                            # 简化处理：假设目标表的主键是 table_name_id 或 id
                            possible_pk = [target_table_name + "_id", "id"]

                            for pk in possible_pk:
                                if pk in table_columns[target_table_name]:
                                    target_col = table_columns[target_table_name][pk]

                                    # 检查数据类型是否兼容
                                    type_compatible = self._is_data_type_compatible(col.data_type, target_col.data_type)

                                    rel = Relationship(
                                        source_table=table.table_name,
                                        source_column=col.column_name,
                                        target_table=target_table_name,
                                        target_column=pk,
                                        relationship_type="many-to-one",
                                        match_rate=0.0,
                                        confidence_score=0.7 if type_compatible else 0.5,  # 命名规则基础分
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
        """计算外键匹配率

        Args:
            db_name: 数据库名
            rel: 关系对象

        Returns:
            匹配率 (0-1)
        """
        try:
            conn = self._get_connection(db_name)
            cursor = conn.cursor()

            # 获取源字段的值
            cursor.execute(
                f"""
                SELECT COUNT(DISTINCT `{rel.source_column}`) as src_count
                FROM `{rel.source_table}`
            """
            )
            src_count = cursor.fetchone()[0]

            if src_count == 0:
                return 0.0

            # 获取匹配的值的数量
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
            logger.error(f"计算匹配率失败：{e}")
            return 0.0
