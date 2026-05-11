"""Logging configuration module"""
import logging
import sys
from datetime import datetime
from typing import Optional


class _TimestampFilter(logging.Filter):
    """Add created timestamp to records without one"""
    def filter(self, record: logging.LogRecord) -> bool:
        if record.created is None or record.created == 0:
            record.created = datetime.now().timestamp()
        return True


class _SuppressLibraryFilter(logging.Filter):
    """Suppress INFO-level logs from third-party libraries to avoid interleaving with progress output"""
    def filter(self, record: logging.LogRecord) -> bool:
        # Suppress httpx retry logs (Retrying request)
        if record.name in ("httpx", "httpcore", "urllib3"):
            return False
        return True


def setup_logging(
    level: Optional[str] = None,
    enable_color: bool = True,
) -> None:
    """Unified logging configuration for the project.

    Example format::

        2026-04-30 14:23:01 [INFO]    core.scanner: Successfully connected to MySQL
        2026-04-30 14:23:01 [WARNING] core.scanner: Table test.t1 does not exist or has no columns
        2026-04-30 14:23:02 [ERROR]   core.semantic_analyzer: LLM call failed: timeout

    Args:
        level: Root log level, defaults to settings.log_level, then INFO.
        enable_color: Whether to enable color in terminal output (Linux/macOS only).
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
    """Unified log format: timestamp | level | module | message"""

    # ANSI colors
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

        # Progress message: use custom format without timestamp and level
        progress_type = getattr(record, "progress_type", None)
        if progress_type:
            msg = record.getMessage()
            fmt = {
                "start": "[*] {msg}",
                "step": "  ├─ {msg}",
                "done": "  └─ {msg}",
                "finish": "[OK] {msg}",
                "field_progress": "  Field {msg}",
                "table_progress": "  {msg}",
            }.get(progress_type, "{msg}")
            return fmt.format(msg=msg)

        # Level name + indent to 10 characters
        levelname = record.levelname.ljust(8)

        # Module name: truncate package path
        module = self._short_module(record.module)

        # Message
        msg = record.getMessage()

        # Assemble
        parts = [f"{ts}  [{levelname}] {module}: {msg}"]

        # Exception info
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
        """Truncate core.semantic_analyzer to semantic_analyzer"""
        if "." in module:
            return module.split(".")[-1]
        return module


# Auto-configure on module load
setup_logging()
