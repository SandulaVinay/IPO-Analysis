"""Unit tests for the database fact audit script."""
import sqlite3
import pytest
from pathlib import Path
from scripts.audit_database_facts import audit_facts_in_database


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_audit.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ipo_id INTEGER,
            field_name TEXT,
            value_text TEXT,
            value_numeric REAL,
            value_type TEXT,
            source_name TEXT,
            source_url TEXT,
            source_tier TEXT,
            verification_status TEXT,
            confidence TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            event_type TEXT,
            entity_name TEXT,
            entity_id TEXT,
            description TEXT,
            metadata_json TEXT
        )
    """)
    # Insert valid verified fact
    cursor.execute("""
        INSERT INTO facts (ipo_id, field_name, value_text, value_numeric, value_type, source_name, source_url, source_tier, verification_status, confidence)
        VALUES (1, 'revenue_latest', '1040.0', 1040.0, 'NUMBER', 'SEBI_RHP', 'https://www.sebi.gov.in/rhp.pdf', 'TIER_1', 'VERIFIED', 'HIGH')
    """)
    # Insert unverified fact (valid)
    cursor.execute("""
        INSERT INTO facts (ipo_id, field_name, value_text, value_numeric, value_type, source_name, source_url, source_tier, verification_status, confidence)
        VALUES (1, 'pat_latest', '125.0', 125.0, 'NUMBER', 'PROSPECTUS_TABLE_CANDIDATE', 'https://www.sebi.gov.in/rhp.pdf', 'TIER_3', 'UNVERIFIED', 'LOW')
    """)
    # Insert invalid fact 1: VERIFIED but missing source URL
    cursor.execute("""
        INSERT INTO facts (ipo_id, field_name, value_text, value_numeric, value_type, source_name, source_url, source_tier, verification_status, confidence)
        VALUES (1, 'cfo_latest', '115.0', 115.0, 'NUMBER', 'SCRAPED', '', 'TIER_1', 'VERIFIED', 'HIGH')
    """)
    # Insert invalid fact 2: VERIFIED but value_type is JSON (unreviewed candidate)
    cursor.execute("""
        INSERT INTO facts (ipo_id, field_name, value_text, value_numeric, value_type, source_name, source_url, source_tier, verification_status, confidence)
        VALUES (1, 'cfo_candidate', '{"raw": "115"}', NULL, 'JSON', 'PROSPECTUS_TABLE_CANDIDATE', 'https://www.sebi.gov.in/rhp.pdf', 'TIER_3', 'VERIFIED', 'HIGH')
    """)
    conn.commit()
    conn.close()
    return db_file


def test_audit_detects_false_verified_statuses(test_db: Path):
    result = audit_facts_in_database(str(test_db), fix=False)
    assert result["total_facts"] == 4
    assert result["verified_count"] == 3
    assert result["invalid_verified_count"] == 2
    assert result["is_clean"] is False

    fields = [item["field_name"] for item in result["invalid_facts"]]
    assert "cfo_latest" in fields
    assert "cfo_candidate" in fields


def test_audit_fix_sanitizes_invalid_facts(test_db: Path):
    fix_result = audit_facts_in_database(str(test_db), fix=True)
    assert fix_result["fixes_applied"] == 2
    assert fix_result["is_clean"] is True

    # Re-audit should now be completely clean
    recheck = audit_facts_in_database(str(test_db), fix=False)
    assert recheck["invalid_verified_count"] == 0
    assert recheck["verified_count"] == 1
    assert recheck["unverified_count"] == 3
    assert recheck["is_clean"] is True
