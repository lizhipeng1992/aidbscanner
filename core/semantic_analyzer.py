"""基于 LLM 的字段语义解析器"""
import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime

from .models import ColumnMetadata, TableMetadata, FieldSemantic, TableSemantic, Relationship, DataCategory, ColumnType
from .scanner import MySQLScanner
from .llm_client import (
    LLMProvider,
    BaseLLMClient,
    ChatMessage,
    ChatResponse,
    LLMError,
    create_llm_client,
)
from .chroma_store import ChromaStore
from .knowledge_base import KnowledgeBase
from config.settings import settings

logger = logging.getLogger(__name__)


class ConsoleProgress:
    """控制台进度输出器"""

    _FORMATS = {
        "start": "[*] {msg}",
        "step": "  ├─ {msg}",
        "done": "  └─ {msg}",
        "finish": "[OK] {msg}",
        "field_progress": "  字段 {msg}",
        "table_progress": "  {msg}",
    }

    def __init__(self, enable: bool = True):
        self.enable = enable
        self.start_time: Optional[datetime] = None
        self._step_start: Optional[datetime] = None

    def start(self, message: str):
        """开始任务"""
        if not self.enable:
            return
        self.start_time = datetime.now()
        print(f"[*] {message}")

    def step(self, message: str):
        """记录步骤"""
        if not self.enable:
            return
        self._step_start = datetime.now()
        print(f"  ├─ {message}")

    def step_done(self, message: Optional[str] = None, duration: float = 0):
        """步骤完成"""
        if not self.enable:
            return
        if message:
            self._log("done", message)

    def field_progress(self, current: int, total: int, field_name: str):
        """字段分析进度"""
        if not self.enable:
            return
        progress_bar = self._progress_bar(current, total, width=20)
        self._log("field_progress", f"[{current}/{total}] {progress_bar} {field_name}")

    def table_progress(self, current: int, total: int, table_name: str, mode: str = None):
        """表分析进度"""
        if not self.enable:
            return
        progress_bar = self._progress_bar(current, total, width=20)
        mode_str = f" [{mode}]" if mode else ""
        self._log("table_progress", f"[{current}/{total}] {progress_bar} {table_name}{mode_str}")

    def finish(self, message: str):
        """任务完成"""
        if not self.enable:
            return
        if self.start_time:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            message = f"{message} (耗时：{elapsed:.1f}s)"
        self._log("finish", message)

    def _progress_bar(self, current: int, total: int, width: int = 20) -> str:
        """生成进度条"""
        filled = int(width * current / total) if total > 0 else 0
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}]"

    def _log(self, progress_type: str, message: str):
        """直接打印进度消息到控制台"""
        fmt = self._FORMATS.get(progress_type, "{msg}")
        print(fmt.format(msg=message))

    def clear_line(self):
        """清除当前行"""
        pass  # 通过 logging 输出时不需要清除行


class SemanticAnalyzer:
    """基于 LLM 的字段语义解析器"""

    def __init__(self, scanner: Optional[MySQLScanner] = None, llm_client: Optional[BaseLLMClient] = None, progress: Optional[ConsoleProgress] = None):
        """初始化语义解析器

        Args:
            scanner: MySQL 扫描器实例，用于获取示例数据
            llm_client: LLM 客户端实例，如不传则根据配置自动创建
            progress: 控制台进度输出器，如不传则默认启用
        """
        self.scanner = scanner
        self._llm_client = llm_client
        self._timeout = None
        self.progress = progress or ConsoleProgress(enable=True)

        # 初始化存储模块
        self.storage_type = settings.semantic_storage_type
        logger.debug(f"初始化语义分析器，存储类型：{self.storage_type}")
        self.storage = None

        if self.storage_type == "milvus":
            try:
                self.storage = KnowledgeBase()
                logger.debug("使用 Milvus 向量存储")
            except Exception as e:
                logger.warning(f"Milvus 存储初始化失败：{e}，将不存储语义数据")
        elif self.storage_type == "chroma":
            try:
                self.storage = ChromaStore(settings.semantic_storage_path)
                logger.debug(f"使用 ChromaDB 存储：{settings.semantic_storage_path}")
            except Exception as e:
                logger.warning(f"ChromaDB 存储初始化失败：{e}，将不存储语义数据")
        else:
            logger.debug(f"未启用语义存储 (storage_type={self.storage_type})")

    def _get_client(self) -> BaseLLMClient:
        """获取 LLM 客户端"""
        if self._llm_client is None:
            provider = settings.llm_provider
            if provider == LLMProvider.OLLAMA:
                logger.debug(f"创建 LLM 客户端：provider={provider}, model={settings.ollama_model}")
                self._llm_client = create_llm_client(
                    LLMProvider.OLLAMA,
                    {"host": settings.ollama_host, "model": settings.ollama_model},
                )
                self._timeout = settings.ollama_timeout
            else:
                logger.debug(f"创建 LLM 客户端：provider={provider}, model={settings.openai_model}")
                self._llm_client = create_llm_client(
                    LLMProvider.OPENAI,
                    {
                        "base_url": settings.openai_base_url,
                        "api_key": settings.openai_api_key,
                        "model": settings.openai_model,
                    },
                )
                self._timeout = settings.openai_timeout
        return self._llm_client

    def _create_field_semantic(
        self,
        column: ColumnMetadata,
        table_name: str,
        db_name: str,
        semantic_data: Dict[str, Any] = None,
        is_default: bool = False,
    ) -> FieldSemantic:
        """创建字段语义对象

        Args:
            column: 字段元数据
            table_name: 表名
            db_name: 数据库名
            semantic_data: LLM 解析的语义数据
            is_default: 是否为默认语义（LLM 调用失败时）

        Returns:
            字段语义对象
        """
        # 根据运行模式设置初始状态
        if settings.effective_runtime_mode == "auto":
            initial_status = ColumnType.AUTO
        else:
            initial_status = ColumnType.PENDING

        if semantic_data:
            return FieldSemantic(
                id=f"{db_name}.{table_name}.{column.column_name}",
                db_name=db_name,
                table_name=table_name,
                column_name=column.column_name,
                data_type=column.data_type,
                **semantic_data,
                status=initial_status,
            )
        else:
            return FieldSemantic(
                id=f"{db_name}.{table_name}.{column.column_name}",
                db_name=db_name,
                table_name=table_name,
                column_name=column.column_name,
                data_type=column.data_type,
                chinese_name=column.column_name,
                business_definition=column.column_comment or "",
                value_rules="",
                related_fields=[],
                data_category=DataCategory.OTHER,
                status=initial_status,
            )

    def analyze_field(
        self,
        column: ColumnMetadata,
        table_name: str,
        db_name: str,
        sample_values: Optional[List[Any]] = None,
    ) -> FieldSemantic:
        """分析单个字段的业务语义

        Args:
            column: 字段元数据
            table_name: 表名
            db_name: 数据库名
            sample_values: 示例数据

        Returns:
            字段语义信息
        """
        logger.debug(f"开始分析字段：{db_name}.{table_name}.{column.column_name}")

        # 构造提示词
        prompt = self._build_field_prompt(column, table_name, db_name, sample_values)

        try:
            client = self._get_client()
            logger.debug(f"调用 LLM 分析字段语义：{table_name}.{column.column_name}")
            response = client.chat(
                messages=[
                    ChatMessage(role="system", content=self._get_system_prompt()),
                    ChatMessage(role="user", content=prompt),
                ],
                timeout=self._timeout,
            )

            logger.debug(f"LLM 响应长度：{len(response.content)} 字符")
            semantic_data = self._parse_semantic_response(response.content)
            logger.debug(f"解析 LLM 响应，获取语义字段：{list(semantic_data.keys()) if semantic_data else '空对象'}")

            # 构建 FieldSemantic 对象
            field_semantic = self._create_field_semantic(
                column, table_name, db_name, semantic_data
            )

            logger.debug(f"完成字段语义分析：{table_name}.{column.column_name}")
            return field_semantic

        except LLMError as e:
            logger.error(f"调用 LLM 失败：{e}")
            return self._create_field_semantic(column, table_name, db_name, is_default=True)
        except Exception as e:
            logger.error(f"分析字段语义失败：{e}")
            return self._create_field_semantic(column, table_name, db_name, is_default=True)

    def analyze_fields_batch(
        self,
        columns: List[ColumnMetadata],
        table_name: str,
        db_name: str,
        sample_data: Optional[Dict[str, List[Any]]] = None,
    ) -> List[FieldSemantic]:
        """批量分析多个字段的业务语义（单次 LLM 调用）

        Args:
            columns: 字段元数据列表
            table_name: 表名
            db_name: 数据库名
            sample_data: 批量示例数据 {column_name: [values]}

        Returns:
            字段语义列表
        """
        if not columns:
            return []

        logger.debug(f"开始批量分析 {len(columns)} 个字段的语义")

        prompt = self._build_batch_field_prompt(columns, table_name, db_name, sample_data)

        try:
            client = self._get_client()
            logger.debug(f"调用 LLM 批量分析字段语义：{table_name}")
            response = client.chat(
                messages=[
                    ChatMessage(role="system", content=self._get_system_prompt()),
                    ChatMessage(role="user", content=prompt),
                ],
                timeout=self._timeout,
            )

            logger.debug(f"LLM 批量响应长度：{len(response.content)} 字符")
            field_list = self._parse_batch_fields_response(response.content)

            # 构建 FieldSemantic 对象
            field_semantics = []
            for semantic_data in field_list:
                # 根据 column_name 匹配原始 column
                col_name = semantic_data.pop("column_name", "")
                column = next((c for c in columns if c.column_name == col_name), None)
                if column:
                    field_semantic = self._create_field_semantic(
                        column, table_name, db_name, semantic_data
                    )
                    field_semantics.append(field_semantic)
                else:
                    logger.warning(f"未找到匹配字段的列：{col_name}")

            logger.debug(f"批量分析完成，成功 {len(field_semantics)}/{len(columns)} 个字段")
            return field_semantics

        except LLMError as e:
            logger.error(f"批量调用 LLM 失败：{e}，降级为逐列分析")
            return self._analyze_fields_fallback(columns, table_name, db_name, sample_data)
        except Exception as e:
            logger.error(f"批量分析字段语义失败：{e}，降级为逐列分析")
            return self._analyze_fields_fallback(columns, table_name, db_name, sample_data)

    def _analyze_fields_fallback(
        self,
        columns: List[ColumnMetadata],
        table_name: str,
        db_name: str,
        sample_data: Optional[Dict[str, List[Any]]] = None,
    ) -> List[FieldSemantic]:
        """降级方案：逐列分析（当批量分析失败时使用）"""
        results = []
        for column in columns:
            sample_values = sample_data.get(column.column_name, []) if sample_data else None
            field_semantic = self.analyze_field(column, table_name, db_name, sample_values)
            results.append(field_semantic)
        return results

    def _build_batch_field_prompt(
        self,
        columns: List[ColumnMetadata],
        table_name: str,
        db_name: str,
        sample_data: Optional[Dict[str, List[Any]]] = None,
    ) -> str:
        """构建批量字段分析提示词"""
        prompt_lines = [
            f"请批量分析以下 MySQL 表的所有字段业务语义：",
            "",
            f"数据库：{db_name}",
            f"表名：{table_name}",
            f"字段数量：{len(columns)}",
            "",
            "请输出 JSON 数组格式，每个元素包含以下字段：",
            '[',
            '  {',
            '    "column_name": "字段名（必须与原字段名完全一致）",',
            '    "chinese_name": "中文业务名称",',
            '    "business_definition": "业务定义描述",',
            '    "value_rules": "取值范围和规则",',
            '    "related_fields": ["关联字段列表"],',
            '    "data_category": "dimension/metric/fact/other"',
            '  }',
            ']',
            "",
            "=== 字段列表 ===",
        ]

        for col in columns:
            prompt_lines.append("")
            prompt_lines.append(f"---")
            prompt_lines.append(f"字段名：{col.column_name}")
            prompt_lines.append(f"数据类型：{col.data_type}")
            if col.column_comment:
                prompt_lines.append(f"字段注释：{col.column_comment}")
            if col.is_primary_key:
                prompt_lines.append("是否主键：是")
            if col.is_auto_increment:
                prompt_lines.append("是否自增：是")
            if col.is_nullable == "YES":
                prompt_lines.append("是否可空：是")
            else:
                prompt_lines.append("是否可空：否")
            if col.column_default is not None:
                prompt_lines.append(f"默认值：{col.column_default}")

            if sample_data and col.column_name in sample_data:
                vals = sample_data[col.column_name]
                if vals:
                    prompt_lines.append("示例值：")
                    for i, val in enumerate(vals[:5], 1):
                        prompt_lines.append(f"  {i}. {val}")

        return "\n".join(prompt_lines)

    def _parse_batch_fields_response(self, response: str) -> List[Dict[str, Any]]:
        """解析批量字段分析的 LLM 响应（JSON 数组格式）"""
        import re

        # 尝试提取 Markdown 代码块中的 JSON 数组
        code_block_match = re.search(r"```json\s*(\[[\s\S]*?\])\s*```", response)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"解析 Markdown JSON 数组失败：{e}")

        # 尝试直接解析 JSON 数组
        try:
            data = json.loads(response)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # 单个对象转为列表
                return [data]
        except json.JSONDecodeError:
            pass

        # 尝试提取不带语言标记的代码块
        code_block_match = re.search(r"```\s*(\[[\s\S]*?\])\s*```", response)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"解析代码块 JSON 数组失败：{e}")

        # 尝试提取多个 JSON 对象
        json_str = self._extract_json_array(response)
        if json_str:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"解析提取的 JSON 数组失败：{e}")

        return []

    def _extract_json_array(self, text: str) -> Optional[str]:
        """从文本中提取 JSON 数组（处理嵌套对象）"""
        import re

        start = text.find("[")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text[start:]):
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return text[start : start + i + 1]

        return None

    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是一个数据语义专家，擅长理解数据库字段背后的业务含义。

你的任务是根据字段的元数据（名称、类型、注释、示例值等）分析其业务语义。

请遵循以下原则：
1. 中文名称：使用简洁、准确的业务术语
2. 业务定义：清晰说明字段的业务含义和使用场景
3. 取值规则：说明字段的取值范围、格式要求、约束条件
4. 关联字段：识别可能与其他表的关联关系
5. 数据分类：判断字段属于维度、指标还是事实

请严格输出 JSON 格式，不要包含其他文本。"""

    def _build_field_prompt(
        self,
        column: ColumnMetadata,
        table_name: str,
        db_name: str,
        sample_values: Optional[List[Any]] = None,
    ) -> str:
        """构建字段分析提示词"""
        prompt_lines = [
            f"请分析以下 MySQL 字段的业务语义：",
            "",
            f"数据库：{db_name}",
            f"表名：{table_name}",
            f"字段名：{column.column_name}",
            f"数据类型：{column.data_type}",
        ]

        if column.column_comment:
            prompt_lines.append(f"字段注释：{column.column_comment}")

        if column.is_primary_key:
            prompt_lines.append("是否主键：是")

        if column.is_auto_increment:
            prompt_lines.append("是否自增：是")

        if column.is_nullable == "YES":
            prompt_lines.append("是否可空：是")
        else:
            prompt_lines.append("是否可空：否")

        if column.column_default is not None:
            prompt_lines.append(f"默认值：{column.column_default}")

        if sample_values:
            prompt_lines.append("")
            prompt_lines.append("示例值：")
            for i, val in enumerate(sample_values[:5], 1):
                prompt_lines.append(f"  {i}. {val}")

        prompt_lines.extend(
            [
                "",
                "请输出 JSON 格式，包含以下字段：",
                '{',
                '  "chinese_name": "中文业务名称",',
                '  "business_definition": "业务定义描述",',
                '  "value_rules": "取值范围和规则",',
                '  "related_fields": ["关联字段列表"],',
                '  "data_category": "dimension/metric/fact/other"',
                '}',
            ]
        )

        return "\n".join(prompt_lines)

    def _parse_semantic_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 返回的语义信息"""
        import re

        # 先尝试提取 Markdown 代码块中的 JSON（处理 ```json ... ``` 格式）
        code_block_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", response)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"解析 Markdown JSON 失败：{e}")

        # 尝试直接解析
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 尝试提取不带语言标记的代码块（处理 ``` ... ``` 格式）
        code_block_match = re.search(r"```\s*(\{[\s\S]*?\})\s*```", response)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"解析代码块 JSON 失败：{e}")

        # 尝试提取第一个完整的 JSON 对象（处理嵌套对象）
        # 使用更精确的正则表达式匹配平衡的花括号
        json_str = self._extract_json_object(response)
        if json_str:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"解析提取的 JSON 失败：{e}")

        # 如果解析失败，返回默认值
        return {}

    def _extract_json_object(self, text: str) -> Optional[str]:
        """从文本中提取 JSON 对象（处理嵌套括号）"""
        import re

        # 查找第一个左花括号
        start = text.find("{")
        if start == -1:
            return None

        # 从第一个左花括号开始，匹配平衡的花括号
        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text[start:]):
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : start + i + 1]

        return None

    def _create_default_semantic(
        self, column: ColumnMetadata, table_name: str, db_name: str
    ) -> FieldSemantic:
        """创建默认语义信息（当 LLM 调用失败时）"""
        return FieldSemantic(
            id=f"{db_name}.{table_name}.{column.column_name}",
            db_name=db_name,
            table_name=table_name,
            column_name=column.column_name,
            data_type=column.data_type,
            chinese_name=column.column_name,  # 使用字段名作为默认中文名
            business_definition=column.column_comment or "",
            value_rules="",
            related_fields=[],
            data_category=DataCategory.OTHER,
            status=ColumnType.PENDING,
        )

    def analyze_table(
        self,
        table: TableMetadata,
        db_name: str,
        sample_data_size: int = 5,
    ) -> TableSemantic:
        """分析整张表的业务语义

        Args:
            table: 表元数据
            db_name: 数据库名
            sample_data_size: 每个字段获取的示例数据条数

        Returns:
            表语义信息
        """
        logger.debug(f"开始分析表：{db_name}.{table.table_name}，共 {len(table.columns)} 个字段")
        self.progress.start(f"分析表 [{db_name}.{table.table_name}]")

        # 分析表名含义
        table_prompt = f"""请分析以下 MySQL 表的业务语义：

数据库：{db_name}
表名：{table.table_name}
表注释：{table.table_comment or '无'}
字段数量：{len(table.columns)}

请输出 JSON 格式：
{{
  "chinese_name": "表中文名称",
  "business_definition": "表业务定义，说明该表存储什么业务数据",
  "data_category": "dimension/metric/fact/other"
}}"""

        try:
            self.progress.step("分析表语义...")
            logger.debug(f"调用 LLM 分析表语义：{table.table_name}")
            client = self._get_client()
            response = client.chat(
                messages=[
                    ChatMessage(role="system", content=self._get_system_prompt()),
                    ChatMessage(role="user", content=table_prompt),
                ],
                timeout=self._timeout,
            )

            table_data = self._parse_semantic_response(response.content)
            self.progress.step_done(f"表中文名：{table_data.get('chinese_name', table.table_name)}")

            # 批量获取示例数据
            sample_data: Optional[Dict[str, List[Any]]] = None
            if self.scanner:
                try:
                    column_names = [c.column_name for c in table.columns]
                    logger.debug(f"批量获取 {len(column_names)} 个字段的示例数据")
                    sample_data = self.scanner.get_sample_data_batch(
                        db_name, table.table_name, column_names, sample_data_size
                    )
                except Exception as e:
                    logger.warning(f"批量获取示例数据失败：{e}，将不使用示例数据")
                    sample_data = {}

            # 批量分析字段语义（单次 LLM 调用）
            self.progress.step("批量分析字段语义...")
            field_semantics = self.analyze_fields_batch(
                table.columns, table.table_name, db_name, sample_data
            )

            self.progress.clear_line()

            # 构建 TableSemantic 对象
            table_semantic = TableSemantic(
                table_name=table.table_name,
                db_name=db_name,
                field_semantics=field_semantics,
                **table_data,
            )

            logger.debug(f"完成表语义分析：{table.table_name} ({len(field_semantics)} 个字段)")

            # 存储语义数据
            if self.storage:
                try:
                    logger.debug(f"存储表语义数据到 {self.storage_type}: {table.table_name}")
                    self.storage.store_table_semantic(table_semantic)
                except Exception as e:
                    logger.warning(f"存储表语义失败：{table.table_name} - {e}")

            self.progress.finish(f"完成 {len(field_semantics)} 个字段分析")
            return table_semantic

        except Exception as e:
            logger.error(f"分析表语义失败：{e}")
            self.progress.clear_line()
            # 返回最小可用结果
            return TableSemantic(
                table_name=table.table_name,
                db_name=db_name,
                chinese_name=table.table_name,
                business_definition=table.table_comment or "",
                data_category=DataCategory.FACT,
                field_semantics=[],
            )

    def verify_relationship(self, rel: Relationship) -> bool:
        """使用 LLM 验证表间关系的语义等价性

        Args:
            rel: 关系对象

        Returns:
            是否验证通过
        """
        logger.debug(f"开始验证关系：{rel.source_table}.{rel.source_column} -> {rel.target_table}.{rel.target_column}")

        prompt = f"""请判断以下两个字段是否构成外键关系：

源表：{rel.source_table}
源字段：{rel.source_column}
目标表：{rel.target_table}
目标字段：{rel.target_column}
值匹配率：{rel.match_rate:.2%}

请分析：
1. 从命名规则看，源字段是否可能引用目标表
2. 从值匹配率看，数据是否支持外键关系
3. 从业务语义看，这种关联是否合理

请输出 JSON 格式：
{{
  "is_valid": true/false,
  "reason": "判断理由"
}}"""

        try:
            logger.debug(f"调用 LLM 验证关系语义，匹配率：{rel.match_rate:.2%}")
            client = self._get_client()
            response = client.chat(
                messages=[
                    ChatMessage(role="system", content="你是一个数据库架构专家，擅长判断表间关系。"),
                    ChatMessage(role="user", content=prompt),
                ],
                timeout=self._timeout,
            )

            data = self._parse_semantic_response(response.content)

            is_valid = data.get("is_valid", False)
            reason = data.get("reason", "")

            if is_valid:
                logger.debug(f"验证通过：{rel.source_table}.{rel.source_column} -> {rel.target_table}.{rel.target_column}")
            else:
                logger.debug(f"验证失败：{reason}")

            return is_valid

        except LLMError as e:
            logger.error(f"验证关系失败：{e}")
            logger.debug(f"LLM 验证失败，使用匹配率降级判断：{rel.match_rate:.2%} >= {settings.relationship_match_threshold:.2%}")
            # 如果 LLM 调用失败，基于匹配率判断
            return rel.match_rate >= settings.relationship_match_threshold

    def batch_analyze_tables(
        self,
        tables: List[TableMetadata],
        db_name: str,
        sample_data_size: int = 5,
    ) -> List[TableSemantic]:
        """批量分析多个表的语义

        Args:
            tables: 表元数据列表
            db_name: 数据库名
            sample_data_size: 每个字段获取的示例数据条数

        Returns:
            表语义列表
        """
        logger.debug(f"开始批量分析 {len(tables)} 张表：{[t.table_name for t in tables]}")
        results = []
        total = len(tables)

        # 显示当前运行模式
        mode = settings.effective_runtime_mode
        mode_desc = "自动保存" if mode == "auto" else "需人工审核"
        self.progress.start(f"批量分析数据库 [{db_name}] 的 {total} 张表 (模式：{mode_desc})")

        for i, table in enumerate(tables, 1):
            self.progress.table_progress(i, total, table.table_name, mode)
            table_semantic = self.analyze_table(table, db_name, sample_data_size)
            results.append(table_semantic)

        logger.debug(f"批量分析完成，成功 {len(results)}/{len(tables)} 张表")
        self.progress.finish(f"完成批量分析，共 {len(results)} 张表 (模式：{mode_desc})")
        return results

    def get_pending_fields(self, db_name: str = None) -> List[Dict[str, Any]]:
        """获取待审核字段列表

        Args:
            db_name: 可选的数据库名过滤

        Returns:
            待审核字段列表
        """
        if self.storage is None:
            logger.warning("存储未初始化，无法获取待审核字段")
            return []

        return self.storage.get_pending_fields(db_name)

    def submit_field_semantic(
        self, field_id: str, calibrated_by: str, modifications: Dict[str, Any] = None
    ) -> bool:
        """提交审核（确认字段）

        Args:
            field_id: 字段唯一标识 (db_name.table_name.column_name)
            calibrated_by: 审核人
            modifications: 可选的修改内容

        Returns:
            是否成功
        """
        if self.storage is None:
            logger.warning("存储未初始化，无法提交字段")
            return False

        return self.storage.submit_field(field_id, calibrated_by, modifications)

    def reject_field_semantic(self, field_id: str) -> bool:
        """拒绝字段

        Args:
            field_id: 字段唯一标识 (db_name.table_name.column_name)

        Returns:
            是否成功
        """
        if self.storage is None:
            logger.warning("存储未初始化，无法拒绝字段")
            return False

        return self.storage.reject_field(field_id)

    def modify_field_semantic(
        self, field_id: str, modifications: Dict[str, Any], calibrated_by: str
    ) -> bool:
        """修改字段并确认

        Args:
            field_id: 字段唯一标识 (db_name.table_name.column_name)
            modifications: 修改内容
            calibrated_by: 修改人

        Returns:
            是否成功
        """
        if self.storage is None:
            logger.warning("存储未初始化，无法修改字段")
            return False

        return self.storage.modify_field(field_id, modifications, calibrated_by)
