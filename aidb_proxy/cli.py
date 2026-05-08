"""aidb-proxy 命令行接口"""
import click

from .service import start_service, stop_service, service_status


@click.group()
def cli():
    """AI Database Proxy - API 服务"""
    pass


@cli.command()
@click.option('--host', default=None, help='后端监听地址 (默认：0.0.0.0)')
@click.option('--port', default=None, help='后端监听端口 (默认：8000)')
@click.option('--web-port', '-w', default=None, help='前端开发服务器端口 (默认：5173)')
@click.option('--no-web', is_flag=True, help='仅启动后端，不启动前端')
def start(host, port, web_port, no_web):
    """启动 API 服务 (后端 + 前端)"""
    try:
        backend_pid, frontend_pid = start_service(
            host=host,
            port=port,
            web_port=web_port,
            start_web=not no_web
        )
        click.echo(f"后端服务已启动 (PID: {backend_pid})")
        if frontend_pid:
            click.echo(f"前端服务已启动 (PID: {frontend_pid})")
        click.echo(f"日志文件：~/.aidb-proxy.log")
        click.echo(f"后端地址：http://localhost:{port or 8000}")
        if not no_web:
            click.echo(f"前端地址：http://localhost:{web_port or 5173}")
    except RuntimeError as e:
        click.echo(f"启动失败：{e}", err=True)
        raise SystemExit(1)


@cli.command()
def stop():
    """停止 API 服务 (后端 + 前端)"""
    try:
        backend_stopped, frontend_stopped = stop_service()
        if backend_stopped:
            click.echo("后端服务已停止")
        else:
            click.echo("后端服务未在运行")
        if frontend_stopped:
            click.echo("前端服务已停止")
        elif not frontend_stopped:  # None 表示前端未启动
            click.echo("前端服务未启动")
    except Exception as e:
        click.echo(f"停止失败：{e}", err=True)
        raise SystemExit(1)


@cli.command()
def status():
    """查看服务状态 (后端 + 前端)"""
    try:
        info = service_status()
        click.echo("=== 后端服务 ===")
        if info["backend_running"]:
            click.echo(f"状态：运行中")
            click.echo(f"PID: {info['backend_pid']}")
            click.echo(f"地址：http://{info['host']}:{info['port']}")
        else:
            click.echo("状态：已停止")

        click.echo("\n=== 前端服务 ===")
        if info["frontend_running"]:
            click.echo(f"状态：运行中")
            click.echo(f"PID: {info['frontend_pid']}")
            click.echo(f"地址：http://localhost:{info['web_port']}")
        else:
            click.echo("状态：未启动")
    except Exception as e:
        click.echo(f"查询失败：{e}", err=True)
        raise SystemExit(1)
