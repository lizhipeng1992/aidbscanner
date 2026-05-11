"""Service process management module"""
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
TIMEOUT = 10  # Stop timeout (seconds)


def _is_process_running(pid: int) -> bool:
    """Check if process is running (cross-platform)"""
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
    """Kill process (cross-platform)"""
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
            time.sleep(0.5)
            if _is_process_running(pid):
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
        except Exception:
            pass
    else:
        try:
            os.kill(pid, sig)
        except (OSError, ProcessLookupError):
            pass


def _find_pid_by_port(port: int) -> Optional[int]:
    """Cross-platform: find PID of process listening on specified port"""
    if sys.platform == "win32":
        return _find_pid_by_port_windows(port)
    elif sys.platform == "darwin":
        return _find_pid_by_port_macos(port)
    else:
        return _find_pid_by_port_linux(port)


def _find_pid_by_port_windows(port: int) -> Optional[int]:
    """Windows: Find PID of process listening on port via netstat"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5
        )
        import re
        for line in result.stdout.splitlines():
            if f":{port}" not in line:
                continue
            if re.search(r'\bLISTENING\b', line):
                parts = line.split()
                for p in reversed(parts):
                    if p.isdigit():
                        return int(p)
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _find_pid_by_port_linux(port: int) -> Optional[int]:
    """Linux: Find PID of process listening on port via ss"""
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
    """macOS: Find PID of process listening on port via lsof"""
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
    """Read PID file"""
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except ValueError:
            _remove_pid(pid_file)
    return None


def _write_pid(pid_file: Path, pid: int) -> None:
    """Write PID file"""
    pid_file.write_text(str(pid))


def _remove_pid(pid_file: Path) -> None:
    """Remove PID file"""
    if pid_file.exists():
        pid_file.unlink()


def _wait_for_process(pid: int) -> None:
    """Wait for process to end"""
    for _ in range(TIMEOUT):
        if not _is_process_running(pid):
            break
        time.sleep(1)

    # SIGKILL on timeout
    if _is_process_running(pid):
        _kill_process(pid, signal.SIGKILL)


def start_service(
    host: Optional[str] = None,
    port: Optional[int] = None,
    web_port: Optional[int] = None,
    start_web: bool = True
) -> Tuple[int, Optional[int]]:
    """
    Start service (backend + frontend)

    Args:
        host: Backend listen address, uses config if None
        port: Backend listen port, uses config if None
        web_port: Frontend port, defaults to 5173 if None
        start_web: Whether to start frontend dev server

    Returns:
        (backend_pid, frontend_pid) PID tuple, frontend_pid is None if frontend not started
    """
    # Check if backend is already running
    backend_pid = _read_pid(BACKEND_PID_FILE)
    if backend_pid and _is_process_running(backend_pid):
        raise RuntimeError(f"Backend service already running (PID: {backend_pid})")

    # Ensure log directory exists
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Build backend command
    backend_cmd = _get_uvicorn_command(host or settings.api_host, port or settings.api_port)

    # Start backend process
    backend_proc = subprocess.Popen(
        backend_cmd,
        stdin=subprocess.DEVNULL,
        stdout=open(LOG_FILE, "a"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    _write_pid(BACKEND_PID_FILE, backend_proc.pid)

    # Start frontend process (if enabled)
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
            # npm unavailable, start backend only
            pass

    return backend_proc.pid, frontend_pid


def stop_service() -> Tuple[bool, Optional[bool]]:
    """
    Stop service (backend + frontend)

    Prefer PID files; if PID files are missing or stale, find and kill processes via port.

    Returns:
        (backend_stopped, frontend_stopped) stop result tuple
        - backend_stopped: Whether backend was successfully stopped (False means not running)
        - frontend_stopped: Whether frontend was successfully stopped (None means not started, False means not running, True means stopped)
    """
    # Stop backend
    backend_pid = _read_pid(BACKEND_PID_FILE)
    backend_killed = False

    if backend_pid:
        if _is_process_running(backend_pid):
            _kill_process(backend_pid)
            _wait_for_process(backend_pid)
            backend_killed = True
        _remove_pid(BACKEND_PID_FILE)

    # PID file did not provide valid PID or PID is stale → kill via port
    if not backend_killed:
        found_pid = _find_pid_by_port(settings.api_port)
        if found_pid:
            _kill_process(found_pid)
            _wait_for_process(found_pid)
            backend_killed = True

    backend_stopped = backend_pid is not None or backend_killed

    # Stop frontend
    frontend_pid = _read_pid(FRONTEND_PID_FILE)
    frontend_killed = False

    if frontend_pid:
        if _is_process_running(frontend_pid):
            _kill_process(frontend_pid)
            _wait_for_process(frontend_pid)
            frontend_killed = True
        _remove_pid(FRONTEND_PID_FILE)

    # PID file did not provide valid PID or PID is stale → kill via port
    found_pid = _find_pid_by_port(5173)
    if found_pid:
        _kill_process(found_pid)
        _wait_for_process(found_pid)
        frontend_killed = True

    # Secondary check: ensure port is released
    if _find_pid_by_port(5173):
        _kill_process(_find_pid_by_port(5173))
        _wait_for_process(_find_pid_by_port(5173))

    frontend_stopped = True if frontend_killed else (None if frontend_pid is None else False)

    return backend_stopped, frontend_stopped


def service_status() -> dict:
    """
    Return service status (backend + frontend)

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
        "web_port": 5173,  # Vite default port
    }


def _get_uvicorn_command(host: str, port: int) -> list:
    """Build uvicorn command"""
    return [
        sys.executable, "-m", "uvicorn",
        "aidb_proxy.main:app",
        "--host", host,
        "--port", str(port),
    ]


def _get_vite_command(port: int) -> list:
    """Build Vite dev server command"""
    # Use npm.cmd on Windows
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    return [
        npm_cmd, "run", "dev",
        "--", "--port", str(port), "--host"
    ]
