"""aidb-proxy CLI interface"""
import click

from .service import start_service, stop_service, service_status


@click.group()
def cli():
    """AI Database Proxy - API Service"""
    pass


@cli.command()
@click.option('--host', default=None, help='Backend listen address (default: 0.0.0.0)')
@click.option('--port', default=None, help='Backend listen port (default: 8000)')
@click.option('--web-port', '-w', default=None, help='Frontend dev server port (default: 5173)')
@click.option('--no-web', is_flag=True, help='Start backend only, without frontend')
def start(host, port, web_port, no_web):
    """Start API Service (backend + frontend)"""
    import os
    try:
        backend_pid, frontend_pid = start_service(
            host=host,
            port=port,
            web_port=web_port,
            start_web=not no_web
        )
        click.echo(f"Backend service started (PID: {backend_pid})")
        if frontend_pid:
            click.echo(f"Frontend service started (PID: {frontend_pid})")
        click.echo(f"Log file: ~/.aidb-proxy.log")
        click.echo(f"Backend address: http://localhost:{port or 8000}")
        if not no_web:
            click.echo(f"Frontend address: http://localhost:{web_port or 5173}")
    except RuntimeError as e:
        click.echo(f"Start failed: {e}", err=True)
        raise SystemExit(1)
    # Exit CLI process to release the terminal
    os._exit(0)


@cli.command()
def stop():
    """Stop API Service (backend + frontend)"""
    try:
        backend_stopped, frontend_stopped = stop_service()
        if backend_stopped:
            click.echo("Backend service stopped")
        else:
            click.echo("Backend service not running")
        if frontend_stopped:
            click.echo("Frontend service stopped")
        elif not frontend_stopped:  # None means frontend was not started
            click.echo("Frontend service not started")
    except Exception as e:
        click.echo(f"Stop failed: {e}", err=True)
        raise SystemExit(1)


@cli.command()
def status():
    """Check service status (backend + frontend)"""
    try:
        info = service_status()
        click.echo("=== Backend Service ===")
        if info["backend_running"]:
            click.echo(f"Status: Running")
            click.echo(f"PID: {info['backend_pid']}")
            click.echo(f"Address: http://{info['host']}:{info['port']}")
        else:
            click.echo("Status: Stopped")

        click.echo("\n=== Frontend Service ===")
        if info["frontend_running"]:
            click.echo(f"Status: Running")
            click.echo(f"PID: {info['frontend_pid']}")
            click.echo(f"Address: http://localhost:{info['web_port']}")
        else:
            click.echo("Status: Not started")
    except Exception as e:
        click.echo(f"Query failed: {e}", err=True)
        raise SystemExit(1)
