import sys
import asyncio
import argparse
import uvicorn

# Configure UTF-8 encoding on Windows console
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from src.database.connection import init_db, AsyncSessionLocal
from src.database.repository import IPORepository
from src.discovery.engine import DiscoveryEngine
from src.web.app import run_pipeline_for_ipo
from src.notifications.orchestrator import NotificationOrchestrator
from src.monitoring.health import HealthMonitor

console = Console(legacy_windows=False, force_terminal=True, safe_box=True, highlight=False)


async def cmd_discover():
    """Run discovery cycle."""
    console.print("[bold blue]Initiating Indian IPO Discovery Cycle...[/bold blue]")
    await init_db()
    async with AsyncSessionLocal() as session:
        engine = DiscoveryEngine(session)
        ipos = await engine.run_discovery()
        console.print(f"[bold green]Discovery cycle complete. {len(ipos)} IPOs identified/updated.[/bold green]")


async def cmd_list():
    """List all tracked IPOs."""
    await init_db()
    async with AsyncSessionLocal() as session:
        repo = IPORepository(session)
        ipos = await repo.list_all_ipos()

        table = Table(title="Tracked Indian IPO Pipeline", header_style="bold magenta")
        table.add_column("Symbol", style="cyan")
        table.add_column("Company Name", style="white")
        table.add_column("Open Date", style="yellow")
        table.add_column("Price Band (Rs)", style="green")
        table.add_column("Issue Size (Rs Cr)", style="blue")
        table.add_column("Status", style="bold")

        for ipo in ipos:
            table.add_row(
                ipo.symbol,
                ipo.company_name,
                str(ipo.verified_open_date or "Announced Soon"),
                f"₹{ipo.min_price} - ₹{ipo.max_price}" if ipo.min_price else "TBD",
                f"₹{ipo.issue_size_cr}" if ipo.issue_size_cr else "TBD",
                ipo.status,
            )

        console.print(table)


async def cmd_analyze(symbol: str, format_type: str = "exec"):
    """Run forensic analysis for an IPO."""
    console.print(f"[bold blue]Running Full Forensic Analysis Pipeline for {symbol}...[/bold blue]")
    await init_db()
    async with AsyncSessionLocal() as session:
        repo = IPORepository(session)
        ipo = await repo.get_ipo_by_symbol(symbol)
        if not ipo:
            console.print(f"[bold red]IPO with symbol '{symbol}' not found in database.[/bold red]")
            return

        data = await run_pipeline_for_ipo(ipo, session)

        if format_type == "full":
            console.print(Panel(data["full_report"], title=f"Full Forensic Report - {symbol}", border_style="blue"))
        elif format_type == "copy":
            console.print(Panel(data["copy_mode"], title=f"WhatsApp Copy Mode - {symbol}", border_style="green"))
        else:
            console.print(Panel(data["executive_summary"], title=f"Executive Summary - {symbol}", border_style="cyan"))


async def cmd_notify(symbol: str):
    """Trigger T-2 alert notification."""
    console.print(f"[bold yellow]Triggering T-2 Alert Dispatch for {symbol}...[/bold yellow]")
    await init_db()
    async with AsyncSessionLocal() as session:
        repo = IPORepository(session)
        ipo = await repo.get_ipo_by_symbol(symbol)
        if not ipo:
            console.print(f"[bold red]IPO with symbol '{symbol}' not found.[/bold red]")
            return

        data = await run_pipeline_for_ipo(ipo, session)
        orchestrator = NotificationOrchestrator(session)
        success = await orchestrator.trigger_t_minus_2_alert(ipo.id, data)
        if success:
            console.print(f"[bold green]Alert successfully dispatched with fallback for {symbol}.[/bold green]")
        else:
            console.print(f"[bold red]Alert dispatch failed for {symbol}.[/bold red]")


async def cmd_health():
    """Check health status."""
    await init_db()
    async with AsyncSessionLocal() as session:
        health = await HealthMonitor.get_system_health(session)
        table = Table(title="Subsystems Health Diagnostics", header_style="bold cyan")
        table.add_column("Subsystem", style="white")
        table.add_column("Status", style="bold green")

        for k, v in health.get("subsystems", {}).items():
            badge_clean = v.get("badge", "UNKNOWN").replace("🟢", "[OK]").replace("🟡", "[WARN]").replace("🔴", "[ERR]")
            table.add_row(k.replace("_", " ").title(), badge_clean)

        console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Indian IPO Intelligence System CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # discover
    subparsers.add_parser("discover", help="Run external discovery cycle")

    # list
    subparsers.add_parser("list", help="List all tracked IPOs")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Analyze an IPO symbol")
    p_analyze.add_argument("symbol", type=str, help="IPO symbol e.g. HEXAGON_TECH")
    p_analyze.add_argument("--format", type=str, choices=["exec", "full", "copy"], default="exec", help="Report format")

    # notify
    p_notify = subparsers.add_parser("notify", help="Trigger T-2 notification dispatch")
    p_notify.add_argument("symbol", type=str, help="IPO symbol")

    # health
    subparsers.add_parser("health", help="Check subsystem health")

    # serve
    p_serve = subparsers.add_parser("serve", help="Start Web Dashboard server")
    p_serve.add_argument("--port", type=int, default=8000, help="Port to listen on")

    args = parser.parse_args()

    if args.command == "discover":
        asyncio.run(cmd_discover())
    elif args.command == "list":
        asyncio.run(cmd_list())
    elif args.command == "analyze":
        asyncio.run(cmd_analyze(args.symbol, args.format))
    elif args.command == "notify":
        asyncio.run(cmd_notify(args.symbol))
    elif args.command == "health":
        asyncio.run(cmd_health())
    elif args.command == "serve":
        uvicorn.run("src.web.app:app", host="0.0.0.0", port=args.port, reload=True)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
