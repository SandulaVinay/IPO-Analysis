from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src.database.models import GMPLastSeen, GMPSnapshot
from src.database.repository import IPORepository
from src.discovery.engine import DiscoveryEngine
from src.ingestion import scrapers as scraper_module
from src.ingestion.scrapers import PortalScraper, parse_ipowatch_gmp_rows


OPEN_PAGE = """
<table>
  <tr><th>IPO</th><th>Type</th><th>Status</th><th>Band</th><th>GMP</th></tr>
  <tr><td>Example Industries Limited</td><td>Mainline</td><td>Open</td><td>₹100–₹110</td><td>₹15</td></tr>
  <tr><td>Closed Example</td><td>Mainline</td><td>Allotment Out</td><td>₹70–₹75</td><td>₹12</td></tr>
</table>
"""


# (a) "last seen" timestamp recorded on every successful open-period lookup

@pytest.mark.asyncio
async def test_engine_records_last_seen_for_unchanged_gmp_without_duplicate_row():
    class Session:
        async def commit(self):
            return None

    class Repository:
        def __init__(self, ipo):
            self.ipo = ipo
            self.added = []
            self.seen = []

        async def create_or_update_ipo(self, **_kwargs):
            return self.ipo

        async def latest_gmp_snapshot(self, _ipo_id, source=None):
            # Same value and same upper price as the live quote: an unchanged reading.
            return SimpleNamespace(gmp_value=15.0, upper_price=110.0)

        async def add_gmp(self, **kwargs):
            self.added.append(kwargs)

        async def mark_gmp_seen(self, **kwargs):
            self.seen.append(kwargs)

    class Scraper:
        last_source_status = "SUCCESS"

        async def fetch_upcoming_ipos(self):
            return [{
                "company_name": "Example Industries Limited",
                "symbol": "EXAMPLE",
                "issue_type": "MAINBOARD",
                "max_price": 110.0,
                "min_price": 100.0,
                "document_links": [],
            }]

        async def fetch_live_gmp_for_company(self, _company_name):
            return {
                "gmp_value": 15.0,
                "max_price": 110.0,
                "issue_type": "MAINBOARD",
                "captured_at": "2026-11-20T10:00:00+00:00",
            }

    ipo = SimpleNamespace(
        id=7,
        status="IPO_DISCOVERED",
        issue_type="MAINBOARD",
        max_price=110.0,
        verified_open_date=None,
        verified_close_date=None,
    )
    repo = Repository(ipo)
    engine = DiscoveryEngine(Session())
    engine.repo = repo
    engine.scraper = Scraper()
    await engine.run_discovery()

    assert repo.added == []  # unchanged value: no duplicate reading row
    assert len(repo.seen) == 1
    assert repo.seen[0]["ipo_id"] == 7
    assert repo.seen[0]["source"] == "IPOWATCH"
    assert isinstance(repo.seen[0]["seen_at"], datetime)
    assert repo.seen[0]["seen_at"].tzinfo is None


@pytest.mark.asyncio
async def test_repository_last_seen_upserts_one_row_and_leaves_readings_alone(async_session):
    repo = IPORepository(async_session)
    first = datetime(2026, 11, 19, 8, 0)
    second = datetime(2026, 11, 22, 16, 0)

    await repo.mark_gmp_seen(ipo_id=3, source="IPOWATCH", seen_at=first)
    await repo.mark_gmp_seen(ipo_id=3, source="IPOWATCH", seen_at=second)
    await async_session.commit()

    rows = (await async_session.execute(select(GMPLastSeen))).scalars().all()
    assert len(rows) == 1
    assert rows[0].ipo_id == 3
    assert rows[0].source == "IPOWATCH"
    assert rows[0].last_seen_at == second

    readings = (await async_session.execute(select(GMPSnapshot))).scalars().all()
    assert readings == []


@pytest.mark.asyncio
async def test_engine_does_not_record_last_seen_when_band_does_not_match(monkeypatch):
    class Session:
        async def commit(self):
            return None

    class Repository:
        def __init__(self, ipo):
            self.ipo = ipo
            self.seen = []

        async def create_or_update_ipo(self, **_kwargs):
            return self.ipo

        async def latest_gmp_snapshot(self, _ipo_id, source=None):
            return None

        async def add_gmp(self, **_kwargs):
            raise AssertionError("mismatched band must not store a reading")

        async def mark_gmp_seen(self, **kwargs):
            self.seen.append(kwargs)

    class Scraper:
        last_source_status = "SUCCESS"

        async def fetch_upcoming_ipos(self):
            return [{
                "company_name": "Example Industries Limited",
                "symbol": "EXAMPLE",
                "issue_type": "MAINBOARD",
                "max_price": 110.0,
                "min_price": 100.0,
                "document_links": [],
            }]

        async def fetch_live_gmp_for_company(self, _company_name):
            return {"gmp_value": 15.0, "max_price": 111.0, "issue_type": "MAINBOARD"}

    ipo = SimpleNamespace(
        id=1, status="IPO_DISCOVERED", issue_type="MAINBOARD", max_price=110.0,
        verified_open_date=None, verified_close_date=None,
    )
    repo = Repository(ipo)
    engine = DiscoveryEngine(Session())
    engine.repo = repo
    engine.scraper = Scraper()
    await engine.run_discovery()
    assert repo.seen == []


# (b) raw IPOWATCH status string logged for every parsed row, once per run

@pytest.mark.asyncio
async def test_ipowatch_load_logs_raw_status_once_per_row_per_run(monkeypatch):
    info_lines = []

    async def fake_get(url, headers=None, timeout=None):
        return SimpleNamespace(text=OPEN_PAGE)

    monkeypatch.setattr(scraper_module.http_client, "get", fake_get)
    monkeypatch.setattr(scraper_module.logger, "info", lambda msg, *args: info_lines.append(msg % args if args else msg))

    scraper = PortalScraper()
    await scraper.fetch_live_gmp_for_company("Example Industries Limited")
    await scraper.fetch_live_gmp_for_company("Closed Example")

    status_lines = [line for line in info_lines if "IPOWATCH status" in line]
    assert len(status_lines) == 2  # one per parsed row, not one per lookup
    assert any("Example Industries Limited" in line and "'Open'" in line for line in status_lines)
    assert any("Closed Example" in line and "'Allotment Out'" in line for line in status_lines)


# Closed-day behaviour must not change.

@pytest.mark.asyncio
async def test_closed_status_still_returns_none(monkeypatch):
    async def fake_get(url, headers=None, timeout=None):
        return SimpleNamespace(text=OPEN_PAGE)

    monkeypatch.setattr(scraper_module.http_client, "get", fake_get)
    scraper = PortalScraper()
    assert await scraper.fetch_live_gmp_for_company("Closed Example") is None
    assert parse_ipowatch_gmp_rows(OPEN_PAGE)[1]["status"] == "Allotment Out"
