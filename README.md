# AI Database Scanner

基于 LLM 的数据库语义层扫描工具，能够自动分析数据库表结构并提取业务语义信息。非侵入式式扫描，扫描完成后存入向量数据库，可通过对外提供的REST API接口进行语义关联查询。

## 功能特性

- **元数据扫描**：支持 MySQL、GBase 8s、SQL Server 多种数据库的表结构和字段信息扫描
- **语义分析**：使用 LLM 分析字段和表的业务含义、生成中文名称和业务定义
- **多模型支持**：支持 Ollama 本地模型和 OpenAI 格式接口（OpenAI、Azure、vLLM 等）
- **关系发现**：基于命名规则和数据匹配率发现潜在的外键关系
- **数据分类**：自动识别维度、指标、事实等数据类别
- **向量化存储**：支持 ChromaDB 本地存储和 Milvus 向量数据库两种存储方式
- **审核模式**：支持 auto（自动保存）和 review（人工审核）两种运行模式
- **多接口支持**：提供 FastAPI REST API、CLI 命令行接口和服务进程管理

## 快速开始

### 环境要求

- Python 3.10+
- 数据库（三选一）：
  - **MySQL** 5.7+ / 8.0+（默认）
  - **GBase 8s**（需安装 ODBC 驱动）
  - **SQL Server** 2016+（需安装 pymssql）
- LLM 服务（二选一）：
  - **Ollama** + 本地模型（推荐 `qwen2.5:7b`）
  - **OpenAI 格式接口**（OpenAI API、Azure OpenAI、vLLM 等）

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd aidbscanner

# 安装（推荐，可全局使用 CLI 命令）
pip install -e .

# 或仅安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置数据库和 LLM 连接信息
```

安装后获得两个 CLI 命令：
- `aidb-scan` — 数据库扫描和语义分析
- `aidb-proxy` — API 服务进程管理（start/stop/status）

### 配置说明

编辑 `.env` 文件：

```env
# 数据库连接（DB_TYPE=mysql/gbase/sqlserver）
DB_TYPE=mysql
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_DATABASE=

# Milvus 向量数据库（可选）
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=db_semantics
MILVUS_VECTOR_DIM=1024

# LLM 提供商选择：ollama 或 openai
LLM_PROVIDER=ollama

# Ollama 配置 (当 LLM_PROVIDER=ollama 时使用)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_TIMEOUT=120

# OpenAI 格式接口配置 (当 LLM_PROVIDER=openai 时使用)
# 可用于：OpenAI 官方 API、Azure OpenAI、vLLM、其他兼容接口
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-3.5-turbo
OPENAI_TIMEOUT=120

# 关系匹配阈值 (0-1)
RELATIONSHIP_MATCH_THRESHOLD=0.95

# 示例数据大小
SAMPLE_DATA_SIZE=5

# 语义存储类型：chroma（ChromaDB）或 milvus（向量数据库）
SEMANTIC_STORAGE_TYPE=chroma
SEMANTIC_STORAGE_PATH=./data/chroma

# 运行模式：auto（自动保存）或 review（需人工审核）
RUNTIME_MODE=auto
```

**LLM 提供商说明：**

| 配置项 | Ollama | OpenAI 格式 |
|--------|--------|-------------|
| `LLM_PROVIDER` | `ollama` | `openai` |
| 适用场景 | 本地部署，免费 | 云端 API 或自托管兼容接口 |
| 兼容服务 | Ollama | OpenAI、Azure OpenAI、vLLM、OpenRouter 等 |

## 项目结构

```
aidbscanner/
├── app/                        # 原始 FastAPI 应用
│   ├── __init__.py            # API 端点定义
│   └── schemas.py             # Pydantic 请求/响应模型
├── aidb_proxy/                 # API 代理服务（带进程管理）
│   ├── __init__.py
│   ├── main.py                # FastAPI 应用（与 app/ 功能相同）
│   ├── schemas.py             # Pydantic 模型（与 app/schemas.py 相同）
│   ├── cli.py                 # 服务管理 CLI（start/stop/status）
│   └── service.py             # 跨平台进程管理（PID 文件）
├── cli/                        # 扫描 CLI 接口
│   └── __init__.py            # Click 命令定义
├── config/                     # 配置管理
│   ├── __init__.py
│   └── settings.py            # Pydantic-settings 配置类
├── core/                       # 核心模块
│   ├── __init__.py
│   ├── models.py              # 数据模型（ColumnMetadata, FieldSemantic 等）
│   ├── base_scanner.py        # 扫描器抽象基类
│   ├── scanner.py             # MySQL 扫描器
│   ├── gbase_scanner.py       # GBase 8s 扫描器
│   ├── sqlserver_scanner.py   # SQL Server 扫描器
│   ├── semantic_analyzer.py   # LLM 语义分析器
│   ├── llm_client.py          # LLM 客户端（Ollama/OpenAI）
│   ├── embedding.py           # 文本向量化服务
│   ├── vector_store.py        # Milvus 向量存储
│   ├── knowledge_base.py      # 语义知识库（向量检索）
│   └── chroma_store.py        # ChromaDB 本地存储
├── tests/                      # 单元测试
│   ├── test_models.py         # 数据模型测试
│   ├── test_scanner.py        # 扫描器测试
│   ├── test_semantic_analyzer.py  # 语义分析器测试
│   ├── test_api.py            # API 端点测试
│   ├── test_cli.py            # CLI 命令测试
│   └── test_review.py         # 审核功能测试
├── pyproject.toml             # 项目配置与依赖
├── requirements.txt           # 依赖列表
├── .env.example               # 环境变量示例
└── todo.md                    # 项目进度
```

## 使用方式

### CLI 命令行（aidb-scan）

| 命令 | 描述 |
|------|------|
| `aidb-scan health` | 检查数据库和 LLM 连接状态 |
| `aidb-scan databases` | 列出所有数据库 |
| `aidb-scan tables <db>` | 列出指定数据库的表 |
| `aidb-scan field <db> <table> <column>` | 分析单个字段语义 |
| `aidb-scan analyze <db> <table>` | 分析整张表语义 |
| `aidb-scan scan <db>` | 全量扫描数据库并分析语义 |
| `aidb-scan review-pending` | 列出待审核字段 |
| `aidb-scan review-interactive` | 交互式审核 |
| `aidb-scan review-submit <ids>` | 批量确认字段 |
| `aidb-scan review-reject <ids>` | 批量拒绝字段 |
| `aidb-scan review-modify <id>` | 修改并确认字段 |
| `aidb-scan query <question>` | 自然语言查询数据库语义 |

**性能优化说明：**

- `analyze` 和 `field` 命令已优化为**仅扫描目标表**元数据，不再扫描全库
- 字段语义分析采用**批量 LLM 调用**策略：同一表的所有字段合并为单次 Ollama 请求（而非逐列调用），性能提升约 N 倍（N = 字段数）
- 示例数据采用**批量查询**：单次 SQL 获取所有列的示例值（而非逐列查询）

**示例：**

```bash
# 健康检查
aidb-scan health

# 全量扫描
aidb-scan scan ecommerce --sample-size 5 --verify-relationships

# 交互式审核
aidb-scan review-interactive
# 操作：y=确认, m=修改后确认, n=拒绝, s=跳过

# 自然语言查询
aidb-scan query "订单表有哪些字段" --top-k 5
```

### API 代理服务（aidb-proxy）

`aidb-proxy` 提供与 `app/` 相同的全部 API 端点，但增加了服务进程管理功能：

```bash
# 启动服务（后台运行）
aidb-proxy start

# 停止服务
aidb-proxy stop

# 查看服务状态
aidb-proxy status

# 前台运行
aidb-proxy start --foreground
```

启动后访问 `http://localhost:8000/docs` 查看交互式 API 文档。

### API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/databases` | 列出所有数据库 |
| GET | `/databases/{db_name}/tables` | 列出指定数据库的表 |
| POST | `/fields/analyze` | 分析字段语义 |
| POST | `/tables/analyze` | 分析表语义 |
| POST | `/relationships/verify` | 验证表间关系 |
| POST | `/discover/relationships` | 发现潜在关系 |
| POST | `/scan` | 全量扫描数据库 |
| GET | `/review/pending` | 获取待审核字段列表 |
| POST | `/review/submit` | 确认字段语义 |
| POST | `/review/reject` | 拒绝字段 |
| POST | `/review/modify` | 修改并确认字段 |
| POST | `/query` | 自然语言查询数据库语义 |

**示例：**

```bash
# 分析字段
curl -X POST http://localhost:8000/fields/analyze \
  -H "Content-Type: application/json" \
  -d '{"db_name": "ecommerce", "table_name": "orders", "column_name": "user_id"}'

# 发现关系
curl -X POST http://localhost:8000/discover/relationships \
  -H "Content-Type: application/json" \
  -d '{"db_name": "ecommerce"}'

# 自然语言查询
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "订单表有哪些字段？", "top_k": 5}'
```

### 运行模式

| 模式 | 说明 | 字段状态 |
|------|------|----------|
| `auto` | LLM 分析结果直接保存 | `AUTO` |
| `review` | LLM 分析结果待人工审核 | `PENDING` |

通过 `.env` 中的 `RUNTIME_MODE` 设置，或命令行临时覆盖：

```bash
RUNTIME_MODE=review aidb-scan scan test_db
```

### Python SDK

```python
from core.base_scanner import BaseDatabaseScanner
from core.semantic_analyzer import SemanticAnalyzer

# 根据 .env 中的 DB_TYPE 自动选择扫描器
from config.settings import settings
if settings.db_type == "gbase":
    from core.gbase_scanner import GBaseScanner
    scanner = GBaseScanner()
elif settings.db_type == "sqlserver":
    from core.sqlserver_scanner import SQLServerScanner
    scanner = SQLServerScanner()
else:
    from core.scanner import MySQLScanner
    scanner = MySQLScanner()

analyzer = SemanticAnalyzer(scanner=scanner)

with scanner:
    # 全量扫描
    tables = scanner.scan_database("ecommerce")
    table_semantics = analyzer.batch_analyze_tables(tables, "ecommerce")

    # 单表扫描（仅扫描指定表，不扫描全库）
    target = scanner.scan_table_only("ecommerce", "orders")
    if target:
        ts = analyzer.analyze_table(target, "ecommerce")
        print(f"{ts.chinese_name} ({ts.table_name})")

    for ts in table_semantics:
        print(f"{ts.chinese_name} ({ts.table_name})")
        for fs in ts.field_semantics:
            print(f"  - {fs.column_name}: {fs.chinese_name}")
```

## 核心概念

### 数据分类

- **Dimension（维度）**：描述业务实体的属性，如用户、产品
- **Metric（指标）**：可量化的业务度量，如销售额、数量
- **Fact（事实）**：记录业务事件的数据，如订单、交易
- **Other（其他）**：无法归类的字段

### 关系发现

1. **命名规则匹配**：识别 `_id` 后缀字段，匹配可能的目标表
2. **数据匹配率计算**：通过 SQL JOIN 计算值匹配率
3. **LLM 验证**：使用 LLM 验证关系的语义合理性

### 存储方式

| 特性 | ChromaDB | Milvus |
|------|----------|--------|
| 部署 | 无需额外服务 | 需部署 Milvus 服务器 |
| 规模 | 中小规模 | 大规模 |
| 语义检索 | 向量相似度搜索 | 向量相似度搜索 |

## 运行测试

```bash
pytest
pytest --cov=core --cov-report=html
```

## 许可证

MIT License
