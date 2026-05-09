"""服务进程管理模块"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

from config.settings import settings

BACKEND_PID_FILE = Path.home() / ".aidb-proxy-backend.pid"
FRONTEND_PID_FILE = Path.home() / ".aidb-proxy-frontend.pid"
LOG_FILE = Path.home() / ".aidb-proxy.log"
TIMEOUT = 10  # 停止超时时间


def _is_process_running(pid: int) -> bool:
    """检查进程是否运行（跨平台）"""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5
            )
            return str(pid) in result.stdout
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


def _find_pid_by_port(port: int) -> Optional[int]:
    """跨平台查找监听指定端口的进程 PID"""
    if sys.platform == "win32":
        return _find_pid_by_port_windows(port)
    elif sys.platform == "darwin":
        return _find_pid_by_port_macos(port)
    else:
        return _find_pid_by_port_linux(port)


def _find_pid_by_port_windows(port: int) -> Optional[int]:
    """Windows: 通过 netstat 查找监听端口的 PID"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5:
                local_addr = parts[1]
                state = parts[3]
                pid_str = parts[4]
                if f":{port}" in local_addr and state == "LISTENING":
                    try:
                        return int(pid_str)
                    except ValueError:
                        continue
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _find_pid_by_port_linux(port: int) -> Optional[int]:
    """Linux: 通过 ss 查找监听端口的 PID"""
    for cmd in [["ss", "-tlnp"], ["netstat", "-tlnp"]]:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line:
                    import re
                    match = re.search(r'pid=(\d+)', line)
                    if match:
                        return int(match.group(1))
        except (subprocess.TimeoutExpired, OSError):
            continue
    return None


def _find_pid_by_port_macos(port: int) -> Optional[int]:
    """macOS: 通过 lsof 查找监听端口的 PID"""
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-n", "-P"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except ValueError:
                    continue
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _read_pid(pid_file: Path) -> Optional[int]:
    """读取 PID 文件"""
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except ValueError:
            _remove_pid(pid_file)
    return None


def _write_pid(pid_file: Path, pid: int) -> None:
    """写入 PID 文件"""
    pid_file.write_text(str(pid))


def _remove_pid(pid_file: Path) -> None:
    """删除 PID 文件"""
    if pid_file.exists():
        pid_file.unlink()


def _wait_for_process(pid: int) -> None:
    """等待进程结束"""
    for _ in range(TIMEOUT):
        if not _is_process_running(pid):
            break
        time.sleep(1)

    # 超时则 SIGKILL
    if _is_process_running(pid):
        _kill_process(pid, signal.SIGKILL)


def start_service(
    host: Optional[str] = None,
    port: Optional[int] = None,
    web_port: Optional[int] = None,
    start_web: bool = True
) -> Tuple[int, Optional[int]]:
    """
    启动服务（后端 + 前端）

    Args:
        host: 后端监听地址，None 则使用配置
        port: 后端监听端口，None 则使用配置
        web_port: 前端端口，None 则使用默认 5173
        start_web: 是否启动前端开发服务器

    Returns:
        (backend_pid, frontend_pid) 进程 PID 元组，前端未启动时 frontend_pid 为 None
    """
    # 检查后端是否已运行
    backend_pid = _read_pid(BACKEND_PID_FILE)
    if backend_pid and _is_process_running(backend_pid):
        raise RuntimeError(f"后端服务已在运行 (PID: {backend_pid})")

    # 确保日志目录存在
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 构建后端命令
    backend_cmd = _get_uvicorn_command(host or settings.api_host, port or settings.api_port)

    # 启动后端进程
    backend_proc = subprocess.Popen(
        backend_cmd,
        stdin=subprocess.DEVNULL,
        stdout=open(LOG_FILE, "a"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    _write_pid(BACKEND_PID_FILE, backend_proc.pid)

    # 启动前端进程（如果启用）
    frontend_pid = None
    if start_web:
        web_dir = Path(__file__).parent.parent / "web"
        frontend_cmd = _get_vite_command(web_port or 5173)
        try:
            frontend_proc = subprocess.Popen(
                frontend_cmd,
                stdin=subprocess.DEVNULL,
                stdout=open(LOG_FILE, "a"),
                stderr=subprocess.STDOUT,
                cwd=str(web_dir),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            _write_pid(FRONTEND_PID_FILE, frontend_proc.pid)
            frontend_pid = frontend_proc.pid
        except FileNotFoundError:
            # npm 不可用时，只启动后端
            pass

    return backend_proc.pid, frontend_pid


def stop_service() -> Tuple[bool, Optional[bool]]:
    """
    停止服务（后端 + 前端）

    优先使用 PID 文件，若 PID 文件缺失或已失效则通过端口查找并杀死进程。

    Returns:
        (backend_stopped, frontend_stopped) 停止结果元组
        - backend_stopped: 后端是否成功停止（False 表示未运行）
        - frontend_stopped: 前端是否成功停止（None 表示未启动，False 表示未运行，True 表示已停止）
    """
    # 停止后端
    backend_pid = _read_pid(BACKEND_PID_FILE)
    backend_killed = False

    if backend_pid:
        if _is_process_running(backend_pid):
            _kill_process(backend_pid)
            _wait_for_process(backend_pid)
            backend_killed = True
        _remove_pid(BACKEND_PID_FILE)

    # PID 文件未提供有效 PID 或 PID 已失效 → 通过端口杀死
    if not backend_killed:
        found_pid = _find_pid_by_port(settings.api_port)
        if found_pid:
            _kill_process(found_pid)
            _wait_for_process(found_pid)
            backend_killed = True

    backend_stopped = backend_pid is not None or backend_killed

    # 停止前端
    frontend_pid = _read_pid(FRONTEND_PID_FILE)
    frontend_killed = False

    if frontend_pid:
        if _is_process_running(frontend_pid):
            _kill_process(frontend_pid)
            _wait_for_process(frontend_pid)
            frontend_killed = True
        _remove_pid(FRONTEND_PID_FILE)

    # PID 文件未提供有效 PID 或 PID 已失效 → 通过端口杀死
    if not frontend_killed:
        found_pid = _find_pid_by_port(5173)
        if found_pid:
            _kill_process(found_pid)
            _wait_for_process(found_pid)
            frontend_killed = True

    frontend_stopped = True if frontend_killed else (None if frontend_pid is None else False)

    return backend_stopped, frontend_stopped


def service_status() -> dict:
    """
    返回服务状态（后端 + 前端）

    Returns:
        {
            "backend_running": bool,
            "backend_pid": int or None,
            "frontend_running": bool,
            "frontend_pid": int or None,
            "host": str,
            "port": int,
            "web_port": int or None,
        }
    """
    backend_pid = _read_pid(BACKEND_PID_FILE)
    backend_running = backend_pid is not None and _is_process_running(backend_pid)

    frontend_pid = _read_pid(FRONTEND_PID_FILE)
    frontend_running = frontend_pid is not None and _is_process_running(frontend_pid)

    return {
        "backend_running": backend_running,
        "backend_pid": backend_pid if backend_running else None,
        "frontend_running": frontend_running,
        "frontend_pid": frontend_pid if frontend_running else None,
        "host": settings.api_host,
        "port": settings.api_port,
        "web_port": 5173,  # Vite 默认端口
    }


def _get_uvicorn_command(host: str, port: int) -> list:
    """构建 uvicorn 命令"""
    return [
        sys.executable, "-m", "uvicorn",
        "aidb_proxy.main:app",
        "--host", host,
        "--port", str(port),
    ]


def _get_vite_command(port: int) -> list:
    """构建 Vite 开发服务器命令"""
    # Windows 上使用 npm.cmd
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    return [
        npm_cmd, "run", "dev",
        "--", "--port", str(port), "--host"
    ]
