"""Audit database facts for historical false VERIFIED statuses and missing provenance.

This tool checks whether any fact in the database claims VERIFIED status without
valid provenance (source URL and source name) or if unreviewed JSON candidate facts
were mistakenly persisted as VERIFIED.
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def audit_facts_in_database(db_path: str, fix: bool = False) -> Dict[str, Any]:
    """Inspect facts in target sqlite database and optionally sanitize false VERIFIED rows."""
    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Database file not found: {path}")

    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()

    # Query all facts
    cursor.execute("""
        SELECT id, ipo_id, field_name, value_text, value_numeric, value_type,
               source_name, source_url, source_tier, verification_status, confidence
        FROM facts
    """)
    rows = cursor.fetchall()

    total_facts = len(rows)
    verified_count = 0
    unverified_count = 0
    invalid_facts: List[Dict[str, Any]] = []

    for row in rows:
        (
            fact_id, ipo_id, field_name, value_text, value_numeric,
            value_type, source_name, source_url, source_tier,
            verification_status, confidence
        ) = row

        status = (verification_status or "").strip().upper()
        if status == "VERIFIED":
            verified_count += 1
            issues = []
            if not source_url or not str(source_url).strip().startswith("https://"):
                issues.append("MISSING_OR_INVALID_SOURCE_URL")
            if not source_name or not str(source_name).strip():
                issues.append("MISSING_SOURCE_NAME")
            if (value_type or "").upper() == "JSON":
                issues.append("JSON_CANDIDATE_MARKED_VERIFIED")
            if value_numeric is None and (value_type or "").upper() == "NUMBER":
                issues.append("NUMERIC_FACT_HAS_NO_VALUE")

            if issues:
                invalid_facts.append({
                    "id": fact_id,
                    "ipo_id": ipo_id,
                    "field_name": field_name,
                    "issues": issues,
                })
        else:
            unverified_count += 1

    fixes_applied = 0
    if fix and invalid_facts:
        now_iso = datetime.now(timezone.utc).isoformat()
        for item in invalid_facts:
            fid = item["id"]
            cursor.execute("""
                UPDATE facts
                SET verification_status = 'UNVERIFIED',
                    confidence = 'LOW'
                WHERE id = ?
            """, (fid,))
            fixes_applied += 1

            # Insert audit log if audit_log table exists
            try:
                cursor.execute("""
                    INSERT INTO audit_log (timestamp, event_type, entity_name, entity_id, description, metadata_json)
                    VALUES (?, 'FACT_AUDIT_FIX', 'Fact', ?, ?, ?)
                """, (
                    now_iso,
                    str(fid),
                    f"Sanitized false VERIFIED status to UNVERIFIED: {', '.join(item['issues'])}",
                    json.dumps(item),
                ))
            except sqlite3.OperationalError:
                pass  # audit_log table might not exist in standalone test db

        conn.commit()

    conn.close()

    return {
        "database": str(path),
        "total_facts": total_facts,
        "verified_count": verified_count - (fixes_applied if fix else 0),
        "unverified_count": unverified_count + (fixes_applied if fix else 0),
        "invalid_verified_count": len(invalid_facts),
        "fixes_applied": fixes_applied,
        "invalid_facts": invalid_facts,
        "is_clean": len(invalid_facts) == 0 or (fix and fixes_applied == len(invalid_facts)),
    }


def main():
    parser = argparse.ArgumentParser(description="Audit database facts for false VERIFIED statuses.")
    parser.add_argument("--db", default="./ipo_system.db", help="Path to SQLite database")
    parser.add_argument("--fix", action="store_true", help="Sanitize false VERIFIED records to UNVERIFIED")
    args = parser.parse_args()

    result = audit_facts_in_database(args.db, fix=args.fix)
    print(f"Database: {result['database']}")
    print(f"Total facts: {result['total_facts']}")
    print(f"Verified: {result['verified_count']}")
    print(f"Unverified: {result['unverified_count']}")
    print(f"Invalid VERIFIED facts found: {result['invalid_verified_count']}")
    if args.fix:
        print(f"Fixes applied: {result['fixes_applied']}")

    if result["invalid_facts"] and not args.fix:
        print("\nIssues found:")
        for inv in result["invalid_facts"]:
            print(f"  Fact ID {inv['id']} ({inv['field_name']}): {', '.join(inv['issues'])}")
        sys.exit(1)
    else:
        print("\nAudit passed: No unverified or invalid facts are claiming VERIFIED status.")
        sys.exit(0)


if __name__ == "__main__":
    main()
