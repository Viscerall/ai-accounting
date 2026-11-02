"""
Export approved journal drafts to tidy Excel and upload to Google Drive.

Usage:
    python -m app.drive_export [--draft-ids ID1 ID2] [--since-days 7]
    # atau dari dashboard: button "📤 Push ke GDrive"
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.db import get_conn, list_drafts, get_stats

# ──────────────────────────────────────────────────────────────────────
# Konfigurasi Drive
# ──────────────────────────────────────────────────────────────────────
DRIVE_FOLDER_NAME = "Dawend Reports"
SCOPES = ["drive.file", "drive"]

# Google API CLI wrapper (pakai token ~/.hermes/google_token.json)
GAPI = [
    sys.executable,
    os.path.expanduser(
        "~/AppData/Local/hermes/skills/productivity/google-workspace/scripts/google_api.py"
    ),
]


def gdrive_available() -> bool:
    """True kalau google_api.py CLI tersedia (hanya di mesin lokal)."""
    return Path(GAPI[1]).exists()


# ──────────────────────────────────────────────────────────────────────
# Helpers Excel styling
# ──────────────────────────────────────────────────────────────────────
THIN = Side(style="thin")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FONT = Font(bold=True, size=11)
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT_WHITE = Font(bold=True, size=11, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14, color="1F4E79")
SUB_FONT = Font(bold=True, size=11, color="1F4E79")
NUM_FMT = "#,##0"
THIN_BORDER = Border(bottom=THIN)


def style_header_row(ws, row: int, max_col: int):
    for c in range(1, max_col + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = HEADER_FONT_WHITE
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = BORDER


def style_data_cell(ws, row: int, col: int, is_money: bool = False):
    cell = ws.cell(row=row, column=col)
    cell.border = BORDER
    if is_money:
        cell.number_format = NUM_FMT
        cell.alignment = Alignment(horizontal="right")
    return cell


def auto_width(ws, min_width=12, max_width=40):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max(max_len + 2, min_width), max_width)


# ──────────────────────────────────────────────────────────────────────
# Excel generation
# ──────────────────────────────────────────────────────────────────────
def make_excel(drafts: list[dict], out_path: Path) -> None:
    """Buat workbook .xlsx rapih."""
    wb = openpyxl.Workbook()

    # ── Sheet 1: Ringkasan ──
    ws = wb.active
    ws.title = "Ringkasan"

    # Title block
    ws.cell(row=1, column=1, value="Dawend — Jurnal Mingguan").font = TITLE_FONT
    ws.cell(row=2, column=1, value=f"Export: {date.today().strftime('%d %B %Y')}").font = SUB_FONT
    scope = f"Draft approved (latest {len(drafts)})" if drafts else "Tidak ada draft"
    ws.cell(row=3, column=1, value=scope).font = SUB_FONT

    # Stats row
    stats = get_stats()
    ws.cell(row=5, column=1, value="Total Raw Transaksi").font = HEADER_FONT
    ws.cell(row=5, column=2, value=stats["raw_transactions"])
    ws.cell(row=6, column=1, value="Draft Approved").font = HEADER_FONT
    ws.cell(row=6, column=2, value=stats["approved"])
    ws.cell(row=7, column=1, value="Turnover (Rp)").font = HEADER_FONT
    c = ws.cell(row=7, column=2, value=float(stats.get("turnover", 0)))
    c.number_format = NUM_FMT

    # Ringkasan per akun (agregat semua draft)
    ws.cell(row=9, column=1, value="Rekap Per Akun (semua draft)").font = SUB_FONT
    headers = ["Kode Akun", "Nama Akun", "Tipe", "Total Debit", "Total Kredit", "Saldo Netto"]
    for i, h in enumerate(headers, 1):
        ws.cell(row=10, column=i, value=h)
    style_header_row(ws, 10, len(headers))

    # agregat
    agg = {}
    for d in drafts:
        for item in d.get("items", []):
            key = (item["account_code"], item["account_name"], "ASSET" if "Kas" in item["account_name"] or "Piutang" in item["account_name"] else ("LIABILITY" if "Utang" in item["account_name"] else ("REVENUE" if "Pendapatan" in item["account_name"] else "EXPENSE")))
            if key not in agg:
                agg[key] = {"debit": Decimal("0"), "credit": Decimal("0")}
            agg[key]["debit"] += Decimal(str(item["debit"] or 0))
            agg[key]["credit"] += Decimal(str(item["credit"] or 0))

    row = 11
    for (code, name, typ), vals in sorted(agg.items()):
        ws.cell(row=row, column=1, value=code)
        ws.cell(row=row, column=2, value=name)
        ws.cell(row=row, column=3, value=typ)
        style_data_cell(ws, row, 4, True).value = float(vals["debit"])
        style_data_cell(ws, row, 5, True).value = float(vals["credit"])
        style_data_cell(ws, row, 6, True).value = float(vals["debit"] - vals["credit"])
        for c in range(1, 7):
            ws.cell(row=row, column=c).border = BORDER
        row += 1

    # Total row
    tot_debit = sum(float(v["debit"]) for v in agg.values())
    tot_credit = sum(float(v["credit"]) for v in agg.values())
    ws.cell(row=row, column=1, value="TOTAL").font = Font(bold=True)
    style_data_cell(ws, row, 4, True).value = tot_debit
    style_data_cell(ws, row, 5, True).value = tot_credit
    style_data_cell(ws, row, 6, True).value = tot_debit - tot_credit

    auto_width(ws)
    ws.freeze_panes = "A11"

    # ── Sheet 2: Daftar Draft ──
    ws2 = wb.create_sheet("Daftar Draft")
    h2 = ["Draft No", "Invoice", "Cabang", "Tanggal", "Status", "Total Debit", "Total Kredit", "Baris Jurnal"]
    for i, h in enumerate(h2, 1):
        ws2.cell(row=1, column=i, value=h)
    style_header_row(ws2, 1, len(h2))

    for r, d in enumerate(drafts, 2):
        ws2.cell(row=r, column=1, value=d["draft_no"])
        ws2.cell(row=r, column=2, value=d["external_id"])
        ws2.cell(row=r, column=3, value=d.get("branch_code", "PUSAT"))
        ws2.cell(row=r, column=4, value=str(d["business_date"]))
        ws2.cell(row=r, column=5, value=d["status"])
        style_data_cell(ws2, r, 6, True).value = float(d["total_debit"])
        style_data_cell(ws2, r, 7, True).value = float(d["total_credit"])
        ws2.cell(row=r, column=8, value=len(d.get("items", [])))
        for c in range(1, 9):
            ws2.cell(row=r, column=c).border = BORDER

    auto_width(ws2)
    ws2.freeze_panes = "A2"

    # ── Sheet per Draft ──
    for d in drafts:
        safe = d["draft_no"].replace("/", "-")
        ws3 = wb.create_sheet(safe[:31])
        ws3.cell(row=1, column=1, value=f"{d['draft_no']} — {d['external_id']}").font = TITLE_FONT
        ws3.cell(row=2, column=1, value=f"Cabang: {d.get('branch_code', 'PUSAT')} · Tanggal: {d['business_date']} · Status: {d['status']}").font = SUB_FONT

        h3 = ["#", "Kode Akun", "Nama Akun", "Debit", "Kredit", "Keterangan"]
        for i, h in enumerate(h3, 1):
            ws3.cell(row=4, column=i, value=h)
        style_header_row(ws3, 4, len(h3))

        r = 5
        for item in d.get("items", []):
            ws3.cell(row=r, column=1, value=item["line_no"])
            ws3.cell(row=r, column=2, value=item["account_code"])
            ws3.cell(row=r, column=3, value=item["account_name"])
            style_data_cell(ws3, r, 4, True).value = float(item["debit"] or 0)
            style_data_cell(ws3, r, 5, True).value = float(item["credit"] or 0)
            ws3.cell(row=r, column=6, value=item["description"])
            for c in range(1, 7):
                ws3.cell(row=r, column=c).border = BORDER
            r += 1

        # totals
        ws3.cell(row=r, column=3, value="TOTAL").font = Font(bold=True)
        style_data_cell(ws3, r, 4, True).value = float(d["total_debit"])
        style_data_cell(ws3, r, 5, True).value = float(d["total_credit"])
        for c in range(1, 7):
            ws3.cell(row=r, column=c).border = BORDER

        auto_width(ws3)
        ws3.freeze_panes = "A5"

    wb.save(out_path)


# ──────────────────────────────────────────────────────────────────────
# Drive upload via google_api.py
# ──────────────────────────────────────────────────────────────────────
def _run_gapi(args: list[str]) -> dict:
    """Jalankan google_api.py, return JSON parsed."""
    res = subprocess.run(GAPI + args, capture_output=True, text=True, timeout=120)
    if res.returncode != 0:
        raise RuntimeError(f"gapi failed ({res.returncode}): {res.stderr}")
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return {"raw": res.stdout}


def get_or_create_folder(folder_name: str) -> str:
    """Cari folder; kalau tidak ada, buat baru. Return folder_id."""
    # proper Drive API query: name = '...' and mimeType = 'application/vnd.google-apps.folder'
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    res = _run_gapi(["drive", "search", query, "--max", "1", "--raw-query"])
    for item in res:
        if item.get("name") == folder_name and item.get("mimeType") == "application/vnd.google-apps.folder":
            return item["id"]
    # buat baru
    res = _run_gapi(["drive", "create-folder", folder_name])
    return res["id"]


def upload_excel(filepath: Path, folder_name: str = DRIVE_FOLDER_NAME, name: str | None = None) -> dict:
    """Upload file .xlsx ke folder Drive."""
    folder_id = get_or_create_folder(folder_name)
    fname = name or filepath.name
    res = _run_gapi(["drive", "upload", str(filepath), "--name", fname, "--parent", folder_id])
    return res


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────
def export_to_drive(
    draft_ids: Optional[list[int]] = None,
    since_days: Optional[int] = None,
    only_approved: bool = True,
) -> dict:
    """
    Ekspor draft ke Drive.
    - draft_ids: eksplisit ID draft; jika None, gunakan filter since_days + only_approved.
    - since_days: ambil draft yg created/reviewed_at dalam N hari terakhir (default 7).
    - only_approved: hanya status APPROVED.
    """
    status_filter = "APPROVED" if only_approved else None
    all_drafts = list_drafts(status=status_filter, limit=1000)

    if draft_ids:
        drafts = [d for d in all_drafts if d["id"] in draft_ids]
    elif since_days:
        now_aware = datetime.now(timezone.utc)
        cutoff = now_aware - timedelta(days=since_days)
        drafts = []
        for d in all_drafts:
            dt = d.get("reviewed_at") or d.get("created_at")
            if not dt:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                drafts.append(d)
    else:
        drafts = all_drafts

    if not drafts:
        return {"status": "no_data", "message": "Tidak ada draft yang memenuhi filter"}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "weekly.xlsx"
        make_excel(drafts, tmp_path)
        iso_year, iso_week, _ = date.today().isocalendar()
        fname = f"AI_ACC_WEEKLY_{iso_year}-W{iso_week:02d}.xlsx"
        res = upload_excel(tmp_path, name=fname)
        return {
            "status": "uploaded",
            "draft_count": len(drafts),
            "file_id": res.get("id"),
            "file_name": fname,
            "web_view_link": res.get("webViewLink"),
        }


# ──────────────────────────────────────────────────────────────────────
# CLI entry
# ──────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export jurnal ke Google Drive (Excel)")
    parser.add_argument("--draft-ids", type=int, nargs="*", help="Daftar ID draft spesifik")
    parser.add_argument("--since-days", type=int, default=7, help="Ambil draft N hari terakhir")
    parser.add_argument("--all-status", action="store_true", help="Bukan hanya APPROVED")
    args = parser.parse_args()

    res = export_to_drive(
        draft_ids=args.draft_ids or None,
        since_days=args.since_days,
        only_approved=not args.all_status,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()