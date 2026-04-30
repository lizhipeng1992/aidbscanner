"""服务进程管理模块"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from config.settings import settings

PID_FILE = Path.home() / ".aidb-proxy.pid"
LOG_FILE = Path.home() / ".aidb-proxy.log"
TIMEOUT = 10  # 停止超时时间


def _is_process_running(pid: int) -> bool:
    """检查进程是否运行（跨平台）"""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5
            )
            return f"{pid}" in subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5
            ).stdout
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def _kill_process(pid: int, sig: int = signal.SIGTERM) -> None:
    """杀死进程（跨平台）"""
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        except Exception:
            pass
    else:
        try:
            os.kill(pid, sig)
        except (OSError, ProcessLookupError):
            pass


def start_service(host: Optional[str] = None, port: Optional[int] = None, foreground: bool = False) -> int:
    """
    启动服务

    Args:
        host: 监听地址，None 则使用配置
        port: 监听端口，None 则使用配置
        foreground: 是否前台运行

    Returns:
        进程 PID
    """
    # 检查是否已运行
    pid = _read_pid()
    if pid and _is_process_running(pid):
        raise RuntimeError(f"服务已在运行 (PID: {pid})")

    # 确保日志目录存在
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 构建命令
    cmd = _get_uvicorn_command(host or settings.api_host, port or settings.api_port)

    # 启动进程
    if foreground:
        proc = subprocess.run(cmd)
        return 0
    else:
        proc = subprocess.Popen(
            cmd,
            stdout=open(LOG_FILE, "a"),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        _write_pid(proc.pid)
        return proc.pid


def stop_service() -> bool:
    """停止服务"""
    pid = _read_pid()
    if not pid:
        return False

    if not _is_process_running(pid):
        _remove_pid()
        return False

    # 发送 SIGTERM
    _kill_process(pid)

    # 等待进程结束
    for _ in range(TIMEOUT):
        if not _is_process_running(pid):
            break
        time.sleep(1)

    # 超时则 SIGKILL
    if _is_process_running(pid):
        _kill_process(pid, signal.SIGKILL)

    _remove_pid()
    return True


def service_status() -> dict:
    """
    返回服务状态

    Returns:
        {
            "running": bool,
            "pid": int or None,
            "host": str,
            "port": int,
        }
    """
    pid = _read_pid()
    running = pid is not None and _is_process_running(pid)

    return {
        "running": running,
        "pid": pid if running else None,
        "host": settings.api_host,
        "port": settings.api_port,
    }


def _read_pid() -> Optional[int]:
    """读取 PID 文件"""
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except ValueError:
            _remove_pid()
    return None


def _write_pid(pid: int) -> None:
    """写入 PID 文件"""
    PID_FILE.write_text(str(pid))


def _remove_pid() -> None:
    """删除 PID 文件"""
    if PID_FILE.exists():
        PID_FILE.unlink()


def _get_uvicorn_command(host: str, port: int) -> list:
    """构建 uvicorn 命令"""
    return [
        sys.executable, "-m", "uvicorn",
        "aidb_proxy.main:app",
        "--host", host,
        "--port", str(port),
    ]
