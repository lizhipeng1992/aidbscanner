"""CLI 命令行接口"""
import click
import json
from typing import Optional, List, Dict, Any

from config.settings import settings
from core.scanner import MySQLScanner
from core.semantic_analyzer import SemanticAnalyzer, ConsoleProgress
from core.chroma_store import ChromaStore


def get_scanner() -> MySQLScanner:
    """获取 MySQL 扫描器实例"""
    return MySQLScanner()


def get_analyzer(scanner: Optional[MySQLScanner] = None) -> SemanticAnalyzer:
    """获取语义分析器实例"""
    if scanner is None:
        scanner = get_scanner()
    return SemanticAnalyzer(scanner)


def get_storage() -> ChromaStore:
    """获取 ChromaDB 存储实例"""
    return ChromaStore(settings.semantic_storage_path)


def get_pending_fields(db_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """获取待审核字段列表"""
    storage = get_storage()
    return storage.get_pending_fields(db_name)


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """AI Database Scanner - 基于本地 LLM 的 MySQL 数据库语义层扫描工具"""
    pass


@cli.command()
def health():
    """检查服务健康状态"""
    from core.llm_client import LLMProvider

    mysql_status = "unknown"
    llm_status = "unknown"
    llm_provider = settings.llm_provider.value

    try:
        scanner = get_scanner()
        scanner.list_databases()
        mysql_status = "connected"
    except Exception as e:
        mysql_status = f"error: {e}"

    # 根据配置检查对应的 LLM 服务
    try:
        if llm_provider == "ollama":
            import ollama

            client = ollama.Client(host=settings.ollama_host)
            client.list()
            llm_status = "connected"
        else:
            from openai import OpenAI

            client = OpenAI(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
            )
            client.models.list()
            llm_status = "connected"
    except Exception as e:
        llm_status = f"error: {e}"

    status = "healthy" if mysql_status == "connected" and llm_status == "connected" else "unhealthy"
    result = {
        "status": status,
        "mysql": mysql_status,
        "llm": llm_status,
        "llm_provider": llm_provider,
    }
    click.echo(json.dumps(result, indent=2))


@cli.command()
def databases():
    """列出所有数据库"""
    try:
        scanner = get_scanner()
        databases = scanner.list_databases()
        system_dbs = {"information_schema", "mysql", "performance_schema", "sys"}
        databases = [db for db in databases if db not in system_dbs]

        click.echo("可用数据库:")
        for db in databases:
            click.echo(f"  - {db}")
    except Exception as e:
        click.echo(f"错误：{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("db_name")
def tables(db_name: str):
    """列出指定数据库的所有表"""
    try:
        scanner = get_scanner()
        tables = scanner.scan_database(db_name)

        if not tables:
            click.echo(f"错误：数据库不存在：{db_name}", err=True)
            raise click.Abort()

        click.echo(f"数据库 [{db_name}] 的表:")
        for table in tables:
            click.echo(f"\n  {table.table_name}")
            if table.table_comment:
                click.echo(f"    说明：{table.table_comment}")
            click.echo(f"    引擎：{table.engine}")
            click.echo(f"    字段数：{len(table.columns)}")
    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"错误：{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("db_name")
@click.argument("table_name")
@click.argument("column_name")
def field(db_name: str, table_name: str, column_name: str):
    """分析单个字段的语义"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        target_table = scanner.scan_table_only(db_name, table_name)
        if not target_table:
            click.echo(f"错误：数据库或表不存在：{db_name}.{table_name}", err=True)
            raise click.Abort()

        target_column = next((c for c in target_table.columns if c.column_name == column_name), None)
        if not target_column:
            click.echo(f"错误：字段不存在：{column_name}", err=True)
            raise click.Abort()

        sample_values = scanner.get_sample_data(db_name, table_name, column_name)

        click.echo(f"正在分析字段 [{db_name}.{table_name}.{column_name}]...")
        field_semantic = analyzer.analyze_field(target_column, table_name, db_name, sample_values)

        result = {
            "column_name": field_semantic.column_name,
            "data_type": field_semantic.data_type,
            "chinese_name": field_semantic.chinese_name,
            "business_definition": field_semantic.business_definition,
            "value_rules": field_semantic.value_rules,
            "related_fields": field_semantic.related_fields,
            "data_category": field_semantic.data_category.value,
        }
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"错误：{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("db_name")
@click.argument("table_name")
@click.option("--sample-size", default=5, help="示例数据行数 (1-20)")
def analyze(db_name: str, table_name: str, sample_size: int):
    """分析整张表的语义"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        target_table = scanner.scan_table_only(db_name, table_name)
        if not target_table:
            click.echo(f"错误：数据库或表不存在：{db_name}.{table_name}", err=True)
            raise click.Abort()

        click.echo(f"正在分析表 [{db_name}.{table_name}]...")
        table_semantic = analyzer.analyze_table(target_table, db_name, sample_size)

        result = {
            "table_name": table_semantic.table_name,
            "chinese_name": table_semantic.chinese_name,
            "business_definition": table_semantic.business_definition,
            "data_category": table_semantic.data_category.value,
            "fields": [
                {
                    "column_name": fs.column_name,
                    "data_type": fs.data_type,
                    "chinese_name": fs.chinese_name,
                    "business_definition": fs.business_definition,
                    "data_category": fs.data_category.value,
                }
                for fs in table_semantic.field_semantics
            ],
        }
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"错误：{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("db_name")
@click.option("--sample-size", default=5, help="示例数据行数 (1-20)")
@click.option("--verify-relationships", is_flag=True, default=True, help="验证表间关系")
def scan(db_name: str, sample_size: int, verify_relationships: bool):
    """全量扫描数据库并分析语义"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        click.echo(f"正在扫描数据库 [{db_name}]...")
        tables = scanner.scan_database(db_name)
        if not tables:
            click.echo(f"错误：数据库不存在：{db_name}", err=True)
            raise click.Abort()

        click.echo(f"发现 {len(tables)} 张表，正在分析语义...")
        table_semantics = analyzer.batch_analyze_tables(tables, db_name, sample_size)

        relationships = []
        if verify_relationships:
            click.echo("正在发现表间关系...")
            candidates = scanner.discover_foreign_key_candidates(tables)
            for rel in candidates:
                match_rate = scanner.calculate_match_rate(db_name, rel)
                rel.match_rate = match_rate
                if match_rate >= settings.relationship_match_threshold:
                    is_valid = analyzer.verify_relationship(rel)
                    rel.verified = is_valid
                    relationships.append(
                        {
                            "source_table": rel.source_table,
                            "source_column": rel.source_column,
                            "target_table": rel.target_table,
                            "target_column": rel.target_column,
                            "relationship_type": rel.relationship_type,
                            "match_rate": rel.match_rate,
                            "verified": rel.verified,
                        }
                    )

        result = {
            "database": db_name,
            "tables": [
                {
                    "table_name": ts.table_name,
                    "chinese_name": ts.chinese_name,
                    "business_definition": ts.business_definition,
                    "data_category": ts.data_category.value,
                    "fields": [
                        {
                            "column_name": fs.column_name,
                            "data_type": fs.data_type,
                            "chinese_name": fs.chinese_name,
                            "business_definition": fs.business_definition,
                            "data_category": fs.data_category.value,
                        }
                        for fs in ts.field_semantics
                    ],
                }
                for ts in table_semantics
            ],
            "relationships": relationships,
        }
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"错误：{e}", err=True)
        raise click.Abort()


# ==================== 审核相关命令 ====================


@cli.command()
@click.option("--db-name", default=None, help="过滤指定数据库")
def review_pending(db_name: Optional[str]):
    """列出待审核字段"""
    try:
        pending_fields = get_pending_fields(db_name)

        if not pending_fields:
            click.echo("暂无待审核字段")
            return

        click.echo(f"待审核字段列表 (共 {len(pending_fields)} 个):")
        click.echo("-" * 80)

        for field in pending_fields:
            click.echo(f"字段 ID: {field['field_id']}")
            click.echo(f"  中文名：{field.get('chinese_name', 'N/A')}")
            click.echo(f"  业务定义：{field.get('business_definition', 'N/A')[:50]}...")
            click.echo(f"  数据分类：{field.get('data_category', 'N/A')}")
            click.echo(f"  创建时间：{field.get('created_at', 'N/A')}")
            click.echo("-" * 80)
    except Exception as e:
        click.echo(f"错误：{e}", err=True)
        raise click.Abort()


@cli.command()
@click.option("--db-name", default=None, help="过滤指定数据库")
def review_interactive(db_name: Optional[str]):
    """交互式审核字段"""
    try:
        storage = get_storage()
        pending_fields = get_pending_fields(db_name)

        if not pending_fields:
            click.echo("暂无待审核字段")
            return

        click.echo(f"发现 {len(pending_fields)} 个待审核字段\n")

        for idx, field in enumerate(pending_fields, 1):
            click.echo(f"[{idx}/{len(pending_fields)}] 字段：{field['field_id']}")
            click.echo(f"  中文名：{field.get('chinese_name', 'N/A')}")
            click.echo(f"  业务定义：{field.get('business_definition', 'N/A')}")
            click.echo(f"  取值规则：{field.get('value_rules', 'N/A')}")
            click.echo(f"  数据分类：{field.get('data_category', 'N/A')}")
            click.echo("")

            # 询问操作
            while True:
                action = click.prompt(
                    "请选择操作",
                    type=click.Choice(['y', 'm', 'n', 's'], case_sensitive=False),
                    show_choices=True,
                    show_default=False,
                    value_prompt="y=确认，m=修改，n=拒绝，s=跳过"
                )

                if action == 'y':  # 确认
                    calibrated_by = click.prompt("请输入审核人姓名", default="admin")
                    if storage.submit_field(field['field_id'], calibrated_by):
                        click.echo("[OK] 已确认\n")
                    else:
                        click.echo("[FAIL] 确认失败\n")
                    break

                elif action == 'm':  # 修改
                    click.echo("请输入修改内容（直接回车保持原值）：")
                    chinese_name = click.prompt("中文名", default=field.get('chinese_name', ''))
                    business_definition = click.prompt("业务定义", default=field.get('business_definition', ''))
                    value_rules = click.prompt("取值规则", default=field.get('value_rules', ''))
                    data_category = click.prompt("数据分类 (dimension/metric/fact/other)", default=field.get('data_category', 'other'))

                    modifications = {}
                    if chinese_name and chinese_name != field.get('chinese_name'):
                        modifications['chinese_name'] = chinese_name
                    if business_definition and business_definition != field.get('business_definition'):
                        modifications['business_definition'] = business_definition
                    if value_rules and value_rules != field.get('value_rules'):
                        modifications['value_rules'] = value_rules
                    if data_category and data_category != field.get('data_category'):
                        modifications['data_category'] = data_category

                    calibrated_by = click.prompt("请输入审核人姓名", default="admin")

                    if modifications:
                        if storage.modify_field(field['field_id'], modifications, calibrated_by):
                            click.echo("[OK] 已修改并确认\n")
                        else:
                            click.echo("[FAIL] 修改失败\n")
                    else:
                        if storage.submit_field(field['field_id'], calibrated_by):
                            click.echo("[OK] 已确认（无修改）\n")
                        else:
                            click.echo("[FAIL] 确认失败\n")
                    break

                elif action == 'n':  # 拒绝
                    if click.confirm("确认拒绝此字段？"):
                        if storage.reject_field(field['field_id']):
                            click.echo("[OK] 已拒绝\n")
                        else:
                            click.echo("[FAIL] 拒绝失败\n")
                    break

                elif action == 's':  # 跳过（实际也是拒绝）
                    if storage.reject_field(field['field_id']):
                        click.echo("[SKIP] 已跳过\n")
                    else:
                        click.echo("[FAIL] 跳过失败\n")
                    break

    except click.Abort:
        click.echo("\n审核已取消")
        raise
    except Exception as e:
        click.echo(f"错误：{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("field_ids", nargs=-1)
@click.option("--calibrated-by", default="admin", help="审核人姓名")
def review_submit(field_ids: tuple, calibrated_by: str):
    """批量确认指定字段

    FIELD_IDS: 字段 ID 列表，格式为 db.table.column
    """
    try:
        if not field_ids:
            click.echo("错误：请至少指定一个字段 ID", err=True)
            raise click.Abort()

        storage = get_storage()
        success_count = 0
        fail_count = 0

        for field_id in field_ids:
            if storage.submit_field(field_id, calibrated_by):
                click.echo(f"[OK] 已确认：{field_id}")
                success_count += 1
            else:
                click.echo(f"[FAIL] 确认失败：{field_id}")
                fail_count += 1

        click.echo(f"\n批量确认完成：成功 {success_count}，失败 {fail_count}")
    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"错误：{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("field_ids", nargs=-1)
def review_reject(field_ids: tuple):
    """拒绝指定字段

    FIELD_IDS: 字段 ID 列表，格式为 db.table.column
    """
    try:
        if not field_ids:
            click.echo("错误：请至少指定一个字段 ID", err=True)
            raise click.Abort()

        storage = get_storage()
        success_count = 0
        fail_count = 0

        for field_id in field_ids:
            if storage.reject_field(field_id):
                click.echo(f"[OK] 已拒绝：{field_id}")
                success_count += 1
            else:
                click.echo(f"[FAIL] 拒绝失败：{field_id}")
                fail_count += 1

        click.echo(f"\n批量拒绝完成：成功 {success_count}，失败 {fail_count}")
    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"错误：{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("field_id")
@click.option("--chinese-name", default=None, help="修改中文名")
@click.option("--business-definition", default=None, help="修改业务定义")
@click.option("--value-rules", default=None, help="修改取值规则")
@click.option("--data-category", default=None, help="修改数据分类 (dimension/metric/fact/other)")
@click.option("--calibrated-by", default="admin", help="审核人姓名")
def review_modify(
    field_id: str,
    chinese_name: Optional[str],
    business_definition: Optional[str],
    value_rules: Optional[str],
    data_category: Optional[str],
    calibrated_by: str
):
    """修改并确认字段

    FIELD_ID: 字段 ID，格式为 db.table.column
    """
    try:
        storage = get_storage()

        modifications = {}
        if chinese_name is not None:
            modifications['chinese_name'] = chinese_name
        if business_definition is not None:
            modifications['business_definition'] = business_definition
        if value_rules is not None:
            modifications['value_rules'] = value_rules
        if data_category is not None:
            modifications['data_category'] = data_category

        if not modifications:
            click.echo("警告：未指定任何修改项，将直接确认字段")
            if storage.submit_field(field_id, calibrated_by):
                click.echo(f"[OK] 已确认：{field_id}")
            else:
                click.echo(f"[FAIL] 确认失败：{field_id}")
            return

        if storage.modify_field(field_id, modifications, calibrated_by):
            click.echo(f"[OK] 已修改并确认：{field_id}")
            click.echo("修改内容：")
            for key, value in modifications.items():
                click.echo(f"  {key}: {value}")
        else:
            click.echo(f"[FAIL] 修改失败：{field_id}")
    except Exception as e:
        click.echo(f"错误：{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("question")
@click.option("--db-name", default=None, help="过滤指定数据库")
@click.option("--top-k", default=10, help="返回结果数量 (1-50)")
def query(question: str, db_name: Optional[str], top_k: int):
    """自然语言查询数据库语义"""
    try:
        from rich.markdown import Markdown
        from core.query_engine import QueryEngine

        click.echo(f"正在查询：{question}\n")

        engine = QueryEngine()
        result = engine.query(question=question, db_name=db_name, top_k=top_k)

        if result.has_error:
            click.echo(f"[bold red]错误：{result.error_message}[/bold red]\n")

        click.echo(f"[bold]回答：[/bold]{result.answer}\n")

        if result.fields:
            click.echo(f"[bold]相关字段（共 {len(result.fields)} 个）：[/bold]")
            for field in result.fields:
                click.echo(f"  - [cyan]{field['table_name']}.{field['column_name']}[/cyan]")
                if field.get("chinese_name"):
                    click.echo(f"    中文名：{field['chinese_name']}")
                if field.get("business_definition"):
                    click.echo(f"    业务定义：{field['business_definition']}")
                if field.get("relevance_score", 0) > 0:
                    click.echo(f"    相关度：{field['relevance_score']:.2f}")
                click.echo("")

        if result.tables:
            click.echo(f"[bold]相关表（共 {len(result.tables)} 张）：[/bold]")
            for table in result.tables:
                click.echo(f"  - [magenta]{table['db_name']}.{table['table_name']}[/magenta]")
                if table.get("chinese_name"):
                    click.echo(f"    中文名：{table['chinese_name']}")
                if table.get("business_definition"):
                    click.echo(f"    业务定义：{table['business_definition']}")
                click.echo("")

    except Exception as e:
        click.echo(f"[bold red]错误：{e}[/bold red]", err=True)
        raise click.Abort()


if __name__ == "__main__":
    cli()
