#!/usr/bin/env python3
"""Audit every table in the N.O.M.A.D. SQLite database.

Reports row counts per table and flags empty/unused tables.

Usage:
    python scripts/audit_tables.py [path/to/nomad.db]

If no path is given, falls back to the configured data directory.
"""

import os
import sys
import sqlite3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def audit(db_path: str) -> list[dict]:
    """Return a list of {table, row_count} dicts for every user table."""
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]

        results = []
        for table in tables:
            # Use a safe f-string here; table names come from sqlite_master, not user input
            count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            results.append({"table": table, "row_count": count})
        return results
    finally:
        conn.close()


def main():
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        from config import get_data_dir
        db_path = os.path.join(get_data_dir(), "nomad.db")

    if not os.path.isfile(db_path):
        print(f"ERROR: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    results = audit(db_path)

    # Pretty print
    max_name = max(len(r["table"]) for r in results) if results else 10
    total_rows = 0
    empty_tables = []

    print(f"\n{'Table':<{max_name + 2}} {'Rows':>10}")
    print("-" * (max_name + 14))

    for r in sorted(results, key=lambda x: -x["row_count"]):
        count = r["row_count"]
        total_rows += count
        marker = "  <-- EMPTY" if count == 0 else ""
        print(f"{r['table']:<{max_name + 2}} {count:>10}{marker}")
        if count == 0:
            empty_tables.append(r["table"])

    print("-" * (max_name + 14))
    print(f"{'TOTAL':<{max_name + 2}} {total_rows:>10}")
    print(f"\nTables: {len(results)}  |  Non-empty: {len(results) - len(empty_tables)}  |  Empty: {len(empty_tables)}")

    if empty_tables:
        print(f"\nEmpty tables ({len(empty_tables)}):")
        for t in sorted(empty_tables):
            print(f"  - {t}")

    return results


if __name__ == "__main__":
    main()
