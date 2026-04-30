"""日志配置模块"""
import logging
import sys
from datetime import datetime
from typing import Optional


class _TimestampFilter(logging.Filter):
    """为无时间戳的 Record 补充 created 字段"""
    def filter(self, record: logging.LogRecord) -> bool:
        if record.created is None or record.created == 0:
            record.created = datetime.now().timestamp()
        return True


class _SuppressLibraryFilter(logging.Filter):
    """抑制第三方库的 INFO 级别日志，避免与进度输出交错"""
    def filter(self, record: logging.LogRecord) -> bool:
        # 抑制 httpx 的重试日志（Retrying request）
        if record.name in ("httpx", "httpcore", "urllib3"):
            return False
        return True


def setup_logging(
    level: Optional[str] = None,
    enable_color: bool = True,
) -> None:
    """统一配置项目日志。

    格式示例::

        2026-04-30 14:23:01 [INFO]    core.scanner: 连接 MySQL 成功
        2026-04-30 14:23:01 [WARNING] core.scanner: 表 test.t1 不存在或无字段
        2026-04-30 14:23:02 [ERROR]   core.semantic_analyzer: 调用 LLM 失败: timeout

    Args:
        level: 根日志级别，默认从 settings.log_level 读取，再默认 INFO。
        enable_color: 是否在终端输出中启用颜色（仅 Linux/macOS 生效）。
    """
    root = logging.getLogger()
    if level is None:
        from config.settings import settings
        level = settings.log_level
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(_TimestampFilter())
    handler.addFilter(_SuppressLibraryFilter())
    handler.setFormatter(_UnifiedFormatter(enable_color=enable_color))
    root.addHandler(handler)


class _UnifiedFormatter(logging.Formatter):
    """统一日志格式：时间 | 级别 | 模块 | 消息"""

    # ANSI 颜色
    _COLORS = {
        "DEBUG": "\033[36m",      # cyan
        "INFO": "\033[32m",       # green
        "WARNING": "\033[33m",    # yellow
        "ERROR": "\033[31m",      # red
        "CRITICAL": "\033[35m",   # magenta
    }
    _RESET = "\033[0m"

    def __init__(self, enable_color: bool = True) -> None:
        super().__init__()
        self.enable_color = enable_color
        self._platform_has_color = sys.stderr.isatty() and sys.platform != "win32"

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")

        # 进度消息：使用自定义格式，不显示时间戳和级别
        progress_type = getattr(record, "progress_type", None)
        if progress_type:
            msg = record.getMessage()
            fmt = {
                "start": "[*] {msg}",
                "step": "  ├─ {msg}",
                "done": "  └─ {msg}",
                "finish": "[OK] {msg}",
                "field_progress": "  字段 {msg}",
                "table_progress": "  {msg}",
            }.get(progress_type, "{msg}")
            return fmt.format(msg=msg)

        # 级别名称 + 缩进到 10 字符
        levelname = record.levelname.ljust(8)

        # 模块名截断包路径
        module = self._short_module(record.module)

        # 消息
        msg = record.getMessage()

        # 组装
        parts = [f"{ts}  [{levelname}] {module}: {msg}"]

        # 异常信息
        if record.exc_info and record.exc_info[0] is not None:
            parts.append(self.formatException(record.exc_info))

        color = ""
        reset = ""
        if self.enable_color and self._platform_has_color:
            color = self._COLORS.get(record.levelname, "")
            reset = self._RESET

        if color:
            parts[0] = f"{color}{parts[0]}{reset}"

        return "\n".join(parts)

    @staticmethod
    def _short_module(module: str) -> str:
        """将 core.semantic_analyzer 简化为 semantic_analyzer"""
        if "." in module:
            return module.split(".")[-1]
        return module


# 模块加载时自动配置
setup_logging()
