"""aidb-proxy 命令行接口"""
import click

from .service import start_service, stop_service, service_status


@click.group()
def cli():
    """AI Database Proxy - API 服务"""
    pass


@cli.command()
@click.option('--host', default=None, help='监听地址 (默认：0.0.0.0)')
@click.option('--port', default=None, help='监听端口 (默认：8000)')
@click.option('--foreground', '-f', is_flag=True, help='前台运行 (不创建后台服务)')
def start(host, port, foreground):
    """启动 API 服务"""
    try:
        pid = start_service(host=host, port=port, foreground=foreground)
        if foreground:
            click.echo("服务已启动 (前台模式)")
        else:
            click.echo(f"服务已启动 (PID: {pid})")
            click.echo(f"日志文件：~/.aidb-proxy.log")
    except RuntimeError as e:
        click.echo(f"启动失败：{e}", err=True)
        raise SystemExit(1)


@cli.command()
def stop():
    """停止 API 服务"""
    try:
        if stop_service():
            click.echo("服务已停止")
        else:
            click.echo("服务未在运行")
    except Exception as e:
        click.echo(f"停止失败：{e}", err=True)
        raise SystemExit(1)


@cli.command()
def status():
    """查看服务状态"""
    try:
        info = service_status()
        if info["running"]:
            click.echo(f"状态：运行中")
            click.echo(f"PID: {info['pid']}")
            click.echo(f"地址：{info['host']}:{info['port']}")
        else:
            click.echo("状态：已停止")
    except Exception as e:
        click.echo(f"查询失败：{e}", err=True)
        raise SystemExit(1)
