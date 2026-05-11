"""CLI command interface"""
import click
import json
from typing import Optional, List, Dict, Any

from config.settings import settings
from core.scanner import MySQLScanner
from core.semantic_analyzer import SemanticAnalyzer, ConsoleProgress
from core.chroma_store import ChromaStore


def get_scanner() -> MySQLScanner:
    """Get MySQL scanner instance"""
    return MySQLScanner()


def get_analyzer(scanner: Optional[MySQLScanner] = None) -> SemanticAnalyzer:
    """Get semantic analyzer instance"""
    if scanner is None:
        scanner = get_scanner()
    return SemanticAnalyzer(scanner)


def get_storage() -> ChromaStore:
    """Get ChromaDB storage instance"""
    return ChromaStore(settings.semantic_storage_path)


def get_pending_fields(db_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get pending field review list"""
    storage = get_storage()
    return storage.get_pending_fields(db_name)


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """AI Database Scanner - MySQL database semantic layer scanner using local LLM"""
    pass


@cli.command()
def health():
    """Check service health status"""
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

    # Check the corresponding LLM service based on configuration
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
    """List all databases"""
    try:
        scanner = get_scanner()
        databases = scanner.list_databases()
        system_dbs = {"information_schema", "mysql", "performance_schema", "sys"}
        databases = [db for db in databases if db not in system_dbs]

        click.echo("Available databases:")
        for db in databases:
            click.echo(f"  - {db}")
    except Exception as e:
        click.echo(f"Error:{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("db_name")
def tables(db_name: str):
    """List all tables in a specified database"""
    try:
        scanner = get_scanner()
        tables = scanner.scan_database(db_name)

        if not tables:
            click.echo(f"Error: Database does not exist: {db_name}", err=True)
            raise click.Abort()

        click.echo(f"Tables in [{db_name}]:")
        for table in tables:
            click.echo(f"\n  {table.table_name}")
            if table.table_comment:
                click.echo(f"    Comment: {table.table_comment}")
            click.echo(f"    Engine: {table.engine}")
            click.echo(f"    Columns: {len(table.columns)}")
    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"Error:{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("db_name")
@click.argument("table_name")
@click.argument("column_name")
def field(db_name: str, table_name: str, column_name: str):
    """Analyze semantics of a single field"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        target_table = scanner.scan_table_only(db_name, table_name)
        if not target_table:
            click.echo(f"Error: Database or table does not exist: {db_name}.{table_name}", err=True)
            raise click.Abort()

        target_column = next((c for c in target_table.columns if c.column_name == column_name), None)
        if not target_column:
            click.echo(f"Error: Field does not exist: {column_name}", err=True)
            raise click.Abort()

        sample_values = scanner.get_sample_data(db_name, table_name, column_name)

        click.echo(f"Analyzing field [{db_name}.{table_name}.{column_name}]...")
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
        click.echo(f"Error:{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("db_name")
@click.argument("table_name")
@click.option("--sample-size", default=5, help="Number of sample rows (1-20)")
def analyze(db_name: str, table_name: str, sample_size: int):
    """Analyze the semantics of an entire table"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        target_table = scanner.scan_table_only(db_name, table_name)
        if not target_table:
            click.echo(f"Error: Database or table does not exist: {db_name}.{table_name}", err=True)
            raise click.Abort()

        click.echo(f"Analyzing table [{db_name}.{table_name}]...")
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
        click.echo(f"Error:{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("db_name")
@click.option("--sample-size", default=5, help="Number of sample rows (1-20)")
@click.option("--verify-relationships", is_flag=True, default=True, help="Verify table relationships")
def scan(db_name: str, sample_size: int, verify_relationships: bool):
    """Full scan of database and semantic analysis"""
    try:
        scanner = get_scanner()
        analyzer = get_analyzer(scanner)

        click.echo(f"Scanning database [{db_name}]...")
        tables = scanner.scan_database(db_name)
        if not tables:
            click.echo(f"Error: Database does not exist: {db_name}", err=True)
            raise click.Abort()

        click.echo(f"Found {len(tables)} tables, analyzing semantics...")
        table_semantics = analyzer.batch_analyze_tables(tables, db_name, sample_size)

        relationships = []
        if verify_relationships:
            click.echo("Discovering table relationships...")
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
        click.echo(f"Error:{e}", err=True)
        raise click.Abort()


# ==================== Review Commands ====================


@cli.command()
@click.option("--db-name", default=None, help="Filter by database")
def review_pending(db_name: Optional[str]):
    """List pending field reviews"""
    try:
        pending_fields = get_pending_fields(db_name)

        if not pending_fields:
            click.echo("No pending field reviews")
            return

        click.echo(f"Pending field reviews (total: {len(pending_fields)}):")
        click.echo("-" * 80)

        for field in pending_fields:
            click.echo(f"Field ID: {field['field_id']}")
            click.echo(f"  Chinese Name: {field.get('chinese_name', 'N/A')}")
            click.echo(f"  Business Definition: {field.get('business_definition', 'N/A')[:50]}...")
            click.echo(f"  Data Category: {field.get('data_category', 'N/A')}")
            click.echo(f"  Created At: {field.get('created_at', 'N/A')}")
            click.echo("-" * 80)
    except Exception as e:
        click.echo(f"Error:{e}", err=True)
        raise click.Abort()


@cli.command()
@click.option("--db-name", default=None, help="Filter by database")
def review_interactive(db_name: Optional[str]):
    """Interactive field review"""
    try:
        storage = get_storage()
        pending_fields = get_pending_fields(db_name)

        if not pending_fields:
            click.echo("No pending field reviews")
            return

        click.echo(f"Found {len(pending_fields)} pending field reviews\n")

        for idx, field in enumerate(pending_fields, 1):
            click.echo(f"[{idx}/{len(pending_fields)}] Field: {field['field_id']}")
            click.echo(f"  Chinese Name: {field.get('chinese_name', 'N/A')}")
            click.echo(f"  Business Definition: {field.get('business_definition', 'N/A')}")
            click.echo(f"  Value Rules: {field.get('value_rules', 'N/A')}")
            click.echo(f"  Data Category: {field.get('data_category', 'N/A')}")
            click.echo("")

            # Ask for action
            while True:
                action = click.prompt(
                    "Choose action",
                    type=click.Choice(['y', 'm', 'n', 's'], case_sensitive=False),
                    show_choices=True,
                    show_default=False,
                    value_prompt="y=Approve, m=Modify, n=Reject, s=Skip"
                )

                if action == 'y':  # Approve
                    calibrated_by = click.prompt("Enter reviewer name", default="admin")
                    if storage.submit_field(field['field_id'], calibrated_by):
                        click.echo("[OK] Approved\n")
                    else:
                        click.echo("[FAIL] Approval failed\n")
                    break

                elif action == 'm':  # Modify
                    click.echo("Enter modifications (press Enter to keep original):")
                    chinese_name = click.prompt("Chinese Name", default=field.get('chinese_name', ''))
                    business_definition = click.prompt("Business Definition", default=field.get('business_definition', ''))
                    value_rules = click.prompt("Value Rules", default=field.get('value_rules', ''))
                    data_category = click.prompt("Data Category (dimension/metric/fact/other)", default=field.get('data_category', 'other'))

                    modifications = {}
                    if chinese_name and chinese_name != field.get('chinese_name'):
                        modifications['chinese_name'] = chinese_name
                    if business_definition and business_definition != field.get('business_definition'):
                        modifications['business_definition'] = business_definition
                    if value_rules and value_rules != field.get('value_rules'):
                        modifications['value_rules'] = value_rules
                    if data_category and data_category != field.get('data_category'):
                        modifications['data_category'] = data_category

                    calibrated_by = click.prompt("Enter reviewer name", default="admin")

                    if modifications:
                        if storage.modify_field(field['field_id'], modifications, calibrated_by):
                            click.echo("[OK] Modified and approved\n")
                        else:
                            click.echo("[FAIL] Modification failed\n")
                    else:
                        if storage.submit_field(field['field_id'], calibrated_by):
                            click.echo("[OK] Approved (no changes)\n")
                        else:
                            click.echo("[FAIL] Approval failed\n")
                    break

                elif action == 'n':  # Reject
                    if click.confirm("Confirm rejection of this field?"):
                        if storage.reject_field(field['field_id']):
                            click.echo("[OK] Rejected\n")
                        else:
                            click.echo("[FAIL] Rejection failed\n")
                    break

                elif action == 's':  # Skip (also rejection)
                    if storage.reject_field(field['field_id']):
                        click.echo("[SKIP] Skipped\n")
                    else:
                        click.echo("[FAIL] Skip failed\n")
                    break

    except click.Abort:
        click.echo("\nReview cancelled")
        raise
    except Exception as e:
        click.echo(f"Error:{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("field_ids", nargs=-1)
@click.option("--calibrated-by", default="admin", help="Reviewer name")
def review_submit(field_ids: tuple, calibrated_by: str):
    """Batch approve specified fields

    FIELD_IDS: Field IDs list, format: db.table.column
    """
    try:
        if not field_ids:
            click.echo("Error: Please specify at least one field ID", err=True)
            raise click.Abort()

        storage = get_storage()
        success_count = 0
        fail_count = 0

        for field_id in field_ids:
            if storage.submit_field(field_id, calibrated_by):
                click.echo(f"[OK] Approved: {field_id}")
                success_count += 1
            else:
                click.echo(f"[FAIL] Approval failed: {field_id}")
                fail_count += 1

        click.echo(f"\nBatch approval complete: {success_count} succeeded, {fail_count} failed")
    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"Error:{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("field_ids", nargs=-1)
def review_reject(field_ids: tuple):
    """Reject specified fields

    FIELD_IDS: Field IDs list, format: db.table.column
    """
    try:
        if not field_ids:
            click.echo("Error: Please specify at least one field ID", err=True)
            raise click.Abort()

        storage = get_storage()
        success_count = 0
        fail_count = 0

        for field_id in field_ids:
            if storage.reject_field(field_id):
                click.echo(f"[OK] Rejected: {field_id}")
                success_count += 1
            else:
                click.echo(f"[FAIL] Rejection failed: {field_id}")
                fail_count += 1

        click.echo(f"\nBatch rejection complete: {success_count} succeeded, {fail_count} failed")
    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"Error:{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("field_id")
@click.option("--chinese-name", default=None, help="Modify Chinese name")
@click.option("--business-definition", default=None, help="Modify business definition")
@click.option("--value-rules", default=None, help="Modify value rules")
@click.option("--data-category", default=None, help="Modify data category (dimension/metric/fact/other)")
@click.option("--calibrated-by", default="admin", help="Reviewer name")
def review_modify(
    field_id: str,
    chinese_name: Optional[str],
    business_definition: Optional[str],
    value_rules: Optional[str],
    data_category: Optional[str],
    calibrated_by: str
):
    """Modify and confirm field

    FIELD_ID: Field ID, format: db.table.column
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
            click.echo("Warning: No modifications specified, approving directly")
            if storage.submit_field(field_id, calibrated_by):
                click.echo(f"[OK] Approved: {field_id}")
            else:
                click.echo(f"[FAIL] Approval failed: {field_id}")
            return

        if storage.modify_field(field_id, modifications, calibrated_by):
            click.echo(f"[OK] Modified and approved: {field_id}")
            click.echo("Modifications:")
            for key, value in modifications.items():
                click.echo(f"  {key}: {value}")
        else:
            click.echo(f"[FAIL] Modification failed: {field_id}")
    except Exception as e:
        click.echo(f"Error:{e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("question")
@click.option("--db-name", default=None, help="Filter by database")
@click.option("--top-k", default=10, help="Number of results (1-50)")
def query(question: str, db_name: Optional[str], top_k: int):
    """Query database semantics with natural language"""
    try:
        from rich.markdown import Markdown
        from core.query_engine import QueryEngine

        click.echo(f"Querying: {question}\n")

        engine = QueryEngine()
        result = engine.query(question=question, db_name=db_name, top_k=top_k)

        if result.has_error:
            click.echo(f"[bold red]Error: {result.error_message}[/bold red]\n")

        click.echo(f"[bold]Answer:[/bold]{result.answer}\n")

        if result.fields:
            click.echo(f"[bold]Related fields (total: {len(result.fields)}):[/bold]")
            for field in result.fields:
                click.echo(f"  - [cyan]{field['table_name']}.{field['column_name']}[/cyan]")
                if field.get("chinese_name"):
                    click.echo(f"    Chinese Name: {field['chinese_name']}")
                if field.get("business_definition"):
                    click.echo(f"    Business Definition: {field['business_definition']}")
                if field.get("relevance_score", 0) > 0:
                    click.echo(f"    Relevance: {field['relevance_score']:.2f}")
                click.echo("")

        if result.tables:
            click.echo(f"[bold]Related tables (total: {len(result.tables)}):[/bold]")
            for table in result.tables:
                click.echo(f"  - [magenta]{table['db_name']}.{table['table_name']}[/magenta]")
                if table.get("chinese_name"):
                    click.echo(f"    Chinese Name: {table['chinese_name']}")
                if table.get("business_definition"):
                    click.echo(f"    Business Definition: {table['business_definition']}")
                click.echo("")

    except Exception as e:
        click.echo(f"[bold red]Error: {e}[/bold red]", err=True)
        raise click.Abort()


if __name__ == "__main__":
    cli()
