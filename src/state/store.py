"""Sanitized JSON state persistence for ephemeral GitHub Actions runners.

Only public IPO metadata and operational event keys belong here. Never write
recipient details, credentials, or notification message bodies to this store.
"""
import json
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import IPO
from src.database.repository import IPORepository


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    def __init__(self, root: Optional[str] = None):
        configured = root or os.getenv("STATE_DIR", ".runtime_state")
        self.root = Path(configured)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root / name

    def _read(self, name: str, default: Dict[str, Any]) -> Dict[str, Any]:
        path = self._path(name)
        if not path.exists():
            return dict(default)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("schema_version") != 1:
                raise ValueError("Unsupported or malformed state schema")
            return value
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"State file {name} is unreadable; refusing to overwrite it.") from exc

    def _write(self, name: str, payload: Dict[str, Any]) -> None:
        payload["schema_version"] = 1
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path(name))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _parse_date(value: Optional[str]):
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    async def restore_ipo_registry(self, session: AsyncSession) -> int:
        """Hydrate the ephemeral SQLite database from public sanitized state."""
        payload = self._read("ipo_registry.json", {"schema_version": 1, "ipos": []})
        records = payload.get("ipos", [])
        if not isinstance(records, list):
            raise RuntimeError("IPO registry must contain a list; refusing to continue.")
        repository = IPORepository(session)
        restored = 0
        for item in records:
            if not isinstance(item, dict) or not item.get("symbol") or not item.get("company_name"):
                continue
            ipo = await repository.create_or_update_ipo(
                symbol=str(item["symbol"]),
                company_name=str(item["company_name"]),
                industry=item.get("industry"),
                issue_type=item.get("issue_type") or "UNKNOWN",
                announced_open_date=self._parse_date(item.get("announced_open_date")),
                announced_close_date=self._parse_date(item.get("announced_close_date")),
                verified_open_date=self._parse_date(item.get("verified_open_date")),
                verified_close_date=self._parse_date(item.get("verified_close_date")),
                min_price=item.get("min_price"),
                max_price=item.get("max_price"),
                lot_size=item.get("lot_size"),
                issue_size_cr=item.get("issue_size_cr"),
                fresh_issue_cr=item.get("fresh_issue_cr"),
                ofs_cr=item.get("ofs_cr"),
            )
            if item.get("status"):
                ipo.status = str(item["status"])
            restored += 1
        await session.commit()
        return restored

    async def save_ipo_registry(self, session: AsyncSession) -> int:
        result = await session.execute(select(IPO).order_by(IPO.symbol))
        ipos = list(result.scalars().all())
        records = []
        for ipo in ipos:
            records.append({
                "symbol": ipo.symbol,
                "company_name": ipo.company_name,
                "industry": ipo.industry,
                "issue_type": ipo.issue_type,
                "status": ipo.status,
                "announced_open_date": ipo.announced_open_date.isoformat() if ipo.announced_open_date else None,
                "announced_close_date": ipo.announced_close_date.isoformat() if ipo.announced_close_date else None,
                "verified_open_date": ipo.verified_open_date.isoformat() if ipo.verified_open_date else None,
                "verified_close_date": ipo.verified_close_date.isoformat() if ipo.verified_close_date else None,
                "min_price": ipo.min_price,
                "max_price": ipo.max_price,
                "lot_size": ipo.lot_size,
                "issue_size_cr": ipo.issue_size_cr,
                "fresh_issue_cr": ipo.fresh_issue_cr,
                "ofs_cr": ipo.ofs_cr,
            })
        self._write("ipo_registry.json", {"schema_version": 1, "updated_at": _utc_now(), "ipos": records})
        return len(records)

    def load_watchlist(self) -> list[Dict[str, Any]]:
        """Load public NSE symbols from the sanitized state branch."""
        payload = self._read("watchlist.json", {"schema_version": 1, "companies": []})
        companies = payload.get("companies", [])
        if not isinstance(companies, list):
            raise RuntimeError("Company watchlist must be a list.")
        normalized = []
        for item in companies:
            if isinstance(item, str) and item.strip():
                entry = {"symbol": item.strip().upper()}
            elif isinstance(item, dict) and isinstance(item.get("symbol"), str) and item["symbol"].strip():
                entry = {**item, "symbol": item["symbol"].strip().upper()}
            else:
                raise RuntimeError("Each watchlist company must be a symbol string or an object with a symbol.")
            if not re.fullmatch(r"[A-Z0-9&._-]{1,30}", entry["symbol"]):
                raise RuntimeError("Watchlist symbol contains unsupported characters.")
            normalized.append(entry)
        return normalized

    def has_seen_event(self, event_key: str) -> bool:
        """Return whether the outbox has ever recorded this event, regardless of delivery status."""
        payload = self._read("notification_outbox.json", {"schema_version": 1, "events": []})
        events = payload.get("events", [])
        return any(isinstance(event, dict) and event.get("event_key") == event_key for event in events)

    def has_processed_event(self, event_key: str) -> bool:
        payload = self._read("processed_events.json", {"schema_version": 1, "processed_event_keys": []})
        keys = payload.get("processed_event_keys", [])
        return event_key in keys if isinstance(keys, list) else False

    def record_event(self, event_key: str, *, event_type: str, symbol: str, event_date: Optional[str], status: str, channel: Optional[str] = None) -> None:
        """Record sanitized event metadata; never include recipients or message text."""
        processed = self._read("processed_events.json", {"schema_version": 1, "processed_event_keys": []})
        keys = processed.get("processed_event_keys", [])
        if not isinstance(keys, list):
            raise RuntimeError("Processed-event ledger is malformed.")
        if status in {"ACCEPTED", "DELIVERED"} and event_key not in keys:
            keys.append(event_key)
        processed["processed_event_keys"] = keys[-2000:]
        processed["updated_at"] = _utc_now()
        self._write("processed_events.json", processed)

        outbox = self._read("notification_outbox.json", {"schema_version": 1, "events": []})
        events = outbox.get("events", [])
        if not isinstance(events, list):
            raise RuntimeError("Notification outbox is malformed.")
        events = [event for event in events if event.get("event_key") != event_key]
        events.append({
            "event_key": event_key,
            "event_type": event_type,
            "symbol": symbol,
            "event_date": event_date,
            "status": status,
            "channel": channel,
            "updated_at": _utc_now(),
        })
        outbox["events"] = events[-1000:]
        outbox["updated_at"] = _utc_now()
        self._write("notification_outbox.json", outbox)

    def latest_run(self, command: str) -> Optional[Dict[str, Any]]:
        """Return the latest sanitized run record for a command."""
        history = self._read("run_history.json", {"schema_version": 1, "runs": []})
        runs = history.get("runs", [])
        if not isinstance(runs, list):
            raise RuntimeError("Run history is malformed.")
        return next((run for run in reversed(runs) if isinstance(run, dict) and run.get("command") == command), None)

    def record_run(self, *, command: str, status: str, detail: str = "") -> None:
        history = self._read("run_history.json", {"schema_version": 1, "runs": []})
        runs = history.get("runs", [])
        if not isinstance(runs, list):
            raise RuntimeError("Run history is malformed.")
        runs.append({
            "timestamp": _utc_now(),
            "command": command,
            "status": status,
            "detail": detail[:300],
        })
        history["runs"] = runs[-200:]
        self._write("run_history.json", history)
