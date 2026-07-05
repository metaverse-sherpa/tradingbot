#!/usr/bin/env python3
"""
Delete load-test web users whose emails match:
    user{digits}@metaversesherpa.io
and have no linked Telegram account (telegram_chat_id IS NULL).

Connects to the VPS PostgreSQL database via DATABASE_URL from GCP secrets.

Usage:
    python3 scripts/delete_test_web_users.py          # dry-run (count only)
    python3 scripts/delete_test_web_users.py --delete  # actually delete
"""

import sys
import os
import re

# Add project root to path so we can import utils_gcp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import utils_gcp
import psycopg2

EMAIL_PATTERN = r"^user\d+@metaversesherpa\.io$"


def main():
    delete_mode = "--delete" in sys.argv

    url = utils_gcp.get_secret("DATABASE_URL")
    if not url:
        print("Error: DATABASE_URL not found in GCP secrets.")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    # Find all matching test users
    cur.execute("""
        SELECT id, email, telegram_chat_id, premium_expiry
        FROM WebUsers
        WHERE email ~ '^user[0-9]+@metaversesherpa\\.io$'
          AND telegram_chat_id IS NULL
    """)
    rows = cur.fetchall()

    # Double-check with Python regex
    matched = [r for r in rows if re.match(EMAIL_PATTERN, r[1])]

    print(f"Found {len(matched)} test web users matching pattern.")

    if not matched:
        print("Nothing to delete.")
        conn.close()
        return

    # Show a sample
    print("\nSample (first 10):")
    for uid, email, tg_id, expiry in matched[:10]:
        print(f"  id={uid}  email={email}  tg={tg_id}  premium_expiry={expiry}")

    if len(matched) > 10:
        print(f"  ... and {len(matched) - 10} more")

    if not delete_mode:
        print(f"\n⚠️  DRY RUN — no rows deleted.")
        print(f"   Re-run with --delete to remove {len(matched)} users.")
        conn.close()
        return

    # --- Destructive section ---
    ids = tuple(r[0] for r in matched)

    # Delete related portfolio history first
    cur.execute(
        "DELETE FROM PortfolioBalanceHistory WHERE user_id IN %s", (ids,)
    )
    print(f"Deleted {cur.rowcount} PortfolioBalanceHistory rows.")

    # Delete related Alpaca trades
    cur.execute(
        "DELETE FROM AlpacaActiveTrades WHERE web_user_id IN %s", (ids,)
    )
    print(f"Deleted {cur.rowcount} AlpacaActiveTrades rows.")

    # Delete the web users
    cur.execute(
        "DELETE FROM WebUsers WHERE id IN %s", (ids,)
    )
    users_deleted = cur.rowcount
    print(f"Deleted {users_deleted} WebUsers rows.")

    conn.commit()
    conn.close()

    print(f"\n✅ Done. Removed {users_deleted} test web users and their related data.")


if __name__ == "__main__":
    main()
