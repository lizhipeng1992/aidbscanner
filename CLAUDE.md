# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Database Semantic Layer Scanner - A Python tool that uses local LLM (Ollama) to analyze MySQL database schemas and extract business semantics from table/column metadata.

## Architecture

The project follows a modular structure with three main components:

**Core Modules:**
- `core/scanner.py` - `MySQLScanner`: Connects to MySQL, extracts table/column metadata, discovers foreign key candidates by naming patterns (`_id` suffix), and calculates relationship match rates
- `core/semantic_analyzer.py` - `SemanticAnalyzer`: Uses Ollama LLM to analyze field/table semantics, generates business definitions, Chinese names, data categories (dimension/metric/fact), and verifies relationships
- `core/models.py` - Pydantic models: `ColumnMetadata`, `TableMetadata`, `FieldSemantic`, `TableSemantic`, `Relationship`, `RAGContext`

**Supporting Modules:**
- `config/settings.py` - `Settings` class using `pydantic-settings`, loads from `.env` file
- `app/__init__.py` - FastAPI application layer (to be implemented)
- `cli/__init__.py` - Click-based CLI interface (to be implemented)

**Key Dependencies:**
- `mysql-connector-python` - MySQL database connection
- `milvus-sdk` - Vector database for semantic storage
- `ollama` - Local LLM client
- `fastapi` + `uvicorn` - Web API server
- `sqlmodel` - ORM layer

## Development Commands

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Run tests:**
```bash
pytest
pytest -v tests/test_*.py  # Run specific test file
```

**Start FastAPI server:**
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

**Environment setup:**
Copy `.env.example` to `.env` and configure:
- MySQL connection (`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`)
- Milvus vector database (`MILVUS_HOST`, `MILVUS_PORT`, `MILVUS_COLLECTION`)
- Ollama LLM (`OLLAMA_HOST`, `OLLAMA_MODEL` - default: `qwen2.5:7b`)

## Key Design Patterns

1. **LLM Integration**: `SemanticAnalyzer` uses system/user prompt pattern with JSON output parsing. Falls back to default semantics on LLM failure.

2. **Foreign Key Discovery**: `MySQLScanner.discover_foreign_key_candidates()` identifies `_id` suffixed columns and matches them to potential target tables (handles singular/plural variations).

3. **Sample Data Usage**: Field analysis fetches sample values (default 5 rows) to inform LLM about actual data patterns.

4. **Relationship Verification**: Two-stage process - first calculate match rate via SQL JOIN, then use LLM to verify semantic validity of the relationship.

5. **RAG Context**: `RAGContext.to_prompt()` converts semantic metadata into LLM-readable format for downstream query tasks.

## Logging Convention

**ALL developer-facing output MUST be in English.** This includes:
- `logger.debug/info/warning/error` messages in all files
- HTTPException detail/message strings in app endpoints
- Module docstrings, class docstrings, method docstrings
- Inline comments
- Field descriptions in Pydantic models

**Exception:** LLM-facing prompts (system prompts, user prompts sent to Ollama/OpenAI) should remain in Chinese since the LLM is designed to respond in Chinese.

## Configuration

Settings are managed via `config.settings.settings` (Pydantic Settings instance). Key thresholds:
- `relationship_match_threshold` (default 0.95): Minimum match rate for foreign key validation
- `sample_data_size` (default 5): Number of sample rows per field
- `ollama_timeout` (default 120s): LLM request timeout
