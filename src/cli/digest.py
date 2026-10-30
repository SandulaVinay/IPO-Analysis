"""Command-line entry point for the daily IPO status digest."""

import asyncio
from rich.console import Console
from rich.table import Table

from src.database.connection import init_db, AsyncSessionLocal
from src.database.repository import IPORepository
from src.reporting.daily_digest import generate_daily_ipo_digest
from src.state.store import StateStore

console = Console(legacy_windows=False, force_terminal=True, safe_box=True, highlight=False)


async def run_digest() -> None:
    await init_db()
    store = StateStore()
    async with AsyncSessionLocal() as session:
        await store.restore_ipo_registry(session)
        repository = IPORepository(session)
        ipos = await repository.list_all_ipos()
        result = await generate_daily_ipo_digest(ipos, store)

    table = Table(title="Daily IPO Status Digest", header_style="bold cyan")
    table.add_column("Metric", style="white")
    table.add_column("Value", style="bold")
    for key in ("status", "notifications_accepted", "channel", "report_path"):
        if key in result:
            table.add_row(key.replace("_", " ").title(), str(result[key]))
    console.print(table)
    if result.get("status") == "FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(run_digest())
