#!/usr/bin/env python
"""CLI tool untuk ingest JSON, recompute, dan demo."""

import sys
import argparse

from app.db import ingest_transaction, list_drafts, list_coa_rows, reset_all, set_draft_status
from app.config import settings


def ingest_sample(json_path: str) -> tuple[int, int]:
    """Ingest dan import satu sample JSON."""
    import json
    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    raw_id, draft_id = ingest_transaction(payload)
    print(f"✅ Ingested: raw_id={raw_id}, draft_id={draft_id}")
    return raw_id, draft_id


def list_samples(status=None):
    """Tampilkan semua draft."""
    drafts = list_drafts(status=status)
    print(f"\n📋 {len(drafts)} drafts:\n")
    for d in drafts:
        status_emoji = {
            "PENDING": "⏳",
            "APPROVED": "✅",
            "REJECTED": "❌",
            "SYNCED": "🔄",
        }.get(d["status"], "❓")
        print(
            f"{status_emoji} {d['draft_no']}: {d['status']} — {d['total_debit']:.2f} "
            f"debit vs {d['total_credit']:.2f} kredit "
            f"(Inv {d['external_id']})"
        )
    print()


def show_coa():
    """Tampilkan COA (slice for demo)."""
    rows = list_coa_rows()
    print(f"\n📊 {len(rows)} COA:\n")
    for r in rows[:20]:
        print(f"{r['account_code']} — {r['account_name']} ({r['account_type']})")
    if len(rows) > 20:
        print(f"... dan {len(rows) - 20} lainnya.")
    print()


def demo_reset():
    """Wipe semua data (tapi tidak hapus COA)."""
    reset_all()
    print("✅ Semua transaction & draft dihapus.")


def approve_draft(draft_id: int, reviewer: str = "Tim Dawend"):
    """Approve atau Reject satu draft."""
    status = input("Apakah APPROVED atau REJECTED? [APPROVED]: ").strip().upper()
    status = status or "APPROVED"
    if status not in {"APPROVED", "REJECTED"}:
        print(f"⚠️ sebenernya gak ada opsi {status}")
    set_draft_status(draft_id, status, reviewer)
    print(f"✅ Status diubah ke {status}")


def main():
    parser = argparse.ArgumentParser(description="CLI untuk Dawend")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # ingest
    ingest_parser = subparsers.add_parser("ingest", help="Ingest satu sample JSON")
    ingest_parser.add_argument("json_path", help="Path ke file JSON sample")

    # list
    list_parser = subparsers.add_parser("list", help="Tampilkan drafts")
    list_parser.add_argument("--status", choices=["PENDING", "APPROVED", "REJECTED", "SYNCED"], help="Filter status")

    # coa
    subparsers.add_parser("coa", help="Tampilkan COA")

    # reset
    subparsers.add_parser("reset", help="Wipe semua data (demo)")

    # approve
    approve_parser = subparsers.add_parser("approve", help="Approve/Reject draft")
    approve_parser.add_argument("draft_id", type=int, help="ID draft")

    args = parser.parse_args()

    # Connect DB dan jalan
    from app.db import get_conn

    # quick sanity
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        print(f"✅ Database terhubung: {settings.database_url}")
    except Exception as e:
        print(f"❌ Gagal connect ke DB: {e}")
        sys.exit(1)

    if args.cmd == "ingest":
        ingest_sample(args.json_path)
        return
    if args.cmd == "list":
        list_samples(status=args.status)
        return
    if args.cmd == "coa":
        show_coa()
        return
    if args.cmd == "reset":
        demo_reset()
        return
    if args.cmd == "approve":
        approve_draft(args.draft_id)
        return


if __name__ == "__main__":
    main()