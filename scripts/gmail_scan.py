r"""
Local Gmail scan CLI — runs outside Docker, connects to localhost:3307.

Usage:
    .venv\Scripts\python.exe scripts\gmail_scan.py
    .venv\Scripts\python.exe scripts\gmail_scan.py --max 200
    .venv\Scripts\python.exe scripts\gmail_scan.py --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

# Insert project root so app/database/utils imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Override MYSQL_HOST before any app module loads — Docker maps db:3306 to localhost:3307
os.environ.setdefault("MYSQL_HOST", "localhost")


def _build_db_url() -> str:
    host = os.environ.get("MYSQL_HOST", "localhost")
    port = os.environ.get("MYSQL_PORT", "3307")
    db = os.environ.get("MYSQL_DATABASE", "subflow")
    user = os.environ.get("MYSQL_USER", "subflow_user")
    pwd = os.environ.get("MYSQL_PASSWORD", "")
    return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan Gmail receipts and save to DB")
    parser.add_argument("--max", type=int, default=100, help="Max emails to fetch (default 100)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse only, no DB writes")
    args = parser.parse_args()

    # Load .env manually so credentials are available
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    # Re-apply host override after dotenv (dotenv may set MYSQL_HOST=db from .env)
    os.environ["MYSQL_HOST"] = "localhost"

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_url = _build_db_url()
    print(f"[DB] Connecting to {db_url.split('@')[1] if '@' in db_url else db_url}")

    engine = create_engine(db_url, pool_pre_ping=True)

    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[DB] Connection OK")
    except Exception as exc:
        print(f"[DB] Connection FAILED: {exc}")
        print("     → Make sure Docker db container is running: docker compose up db -d")
        sys.exit(1)

    if args.dry_run:
        _run_dry(args.max)
        return

    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with Session() as db:
        from app.parsers.importer import run_gmail_import

        print(f"[Gmail] Starting scan (max={args.max}) — browser may open for OAuth…")
        result = run_gmail_import(db, max_results=args.max)

    print("\n── Import Result ──────────────────────")
    print(f"  Fetched      : {result.total_fetched}")
    print(f"  Parsed       : {result.parsed}")
    print(f"  Inserted     : {result.inserted}")
    print(f"  Dup (skipped): {result.skipped_duplicate}")
    print(f"  No amount    : {result.skipped_no_amount}")
    print("───────────────────────────────────────")


def _run_dry(max_results: int) -> None:
    from app.parsers.gmail_auth import get_gmail_service
    from app.parsers.gmail_fetcher import fetch_receipt_emails
    from app.parsers.receipt_parser import parse_receipt

    print(f"[DRY-RUN] Fetching up to {max_results} emails (no DB writes)…")
    service = get_gmail_service()
    emails = fetch_receipt_emails(service, max_results=max_results)

    parsed, no_amount = 0, 0
    for email in emails:
        receipt = parse_receipt(email)
        if receipt:
            parsed += 1
            print(
                f"  [OK] {receipt.service_name:25s} {receipt.amount:>10} {receipt.currency}  [{receipt.billed_at.date()}]  {receipt.raw_subject[:50]}"
            )
        else:
            no_amount += 1

    print(
        f"\n[DRY-RUN] {len(emails)} fetched | {parsed} parseable | {no_amount} skipped (no amount)"
    )


if __name__ == "__main__":
    main()
