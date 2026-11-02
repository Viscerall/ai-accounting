#!/usr/bin/env python
"""
Weekly export: push jurnal APPROVED 7 hari terakhir ke Google Drive (Excel).

Dijalankan otomatis oleh cron setiap hari Minggu. Bisa juga dipanggil manual:

    python scripts/weekly_export.py            # hanya jalan kalau hari Minggu
    python scripts/weekly_export.py --force    # paksa jalan kapan saja
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "weekly_export.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("weekly_export")


def is_sunday() -> bool:
    return date.today().weekday() == 6  # 0=Senin ... 6=Minggu


def main() -> int:
    parser = argparse.ArgumentParser(description="Push jurnal mingguan ke Google Drive")
    parser.add_argument("--force", action="store_true", help="Jalan walau bukan hari Minggu")
    parser.add_argument("--since-days", type=int, default=7, help="Ambil draft N hari terakhir")
    parser.add_argument("--all-status", action="store_true", help="Termasuk selain APPROVED")
    args = parser.parse_args()

    if not args.force and not is_sunday():
        log.info("Bukan hari Minggu — skip. Pakai --force kalau mau jalan sekarang.")
        return 0

    try:
        from app.drive_export import export_to_drive

        log.info("Mulai export (since_days=%s, only_approved=%s)", args.since_days, not args.all_status)
        res = export_to_drive(since_days=args.since_days, only_approved=not args.all_status)
        log.info("Hasil: %s", json.dumps(res, ensure_ascii=False))

        if res.get("status") == "uploaded":
            log.info("✅ %s draft terkirim → %s", res.get("draft_count"), res.get("web_view_link"))
            print(f"EXPORT_OK {res.get('web_view_link')}")
            return 0
        log.warning("Tidak ada data untuk diekspor.")
        print("EXPORT_NO_DATA")
        return 0
    except Exception as exc:  # noqa: BLE001
        log.exception("Export gagal: %s", exc)
        print(f"EXPORT_FAILED {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
