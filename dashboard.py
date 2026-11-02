"""Streamlit dashboard — AI Accounting untuk kafe."""
from __future__ import annotations
import json
import uuid
from decimal import Decimal
from pathlib import Path
import pandas as pd
import streamlit as st
from app.calculator import calculate
from app.auth import require_login
from app.config import settings, db_label
from app.db import get_conn, get_stats, ingest_transaction, list_coa_rows, list_drafts, recompute_draft, reset_all, set_draft_status
from app.mapping_rules import MappingError

SAMPLE_DIR = Path(__file__).parent / "data" / "samples"
REVIEWER = "nizar"
BADGE = {"PENDING": ("⏳", "#fff3cd"), "APPROVED": ("✅", "#d4edda"), "REJECTED": ("❌", "#f8d7da"), "SYNCED": ("🔄", "#d1ecf1")}
st.set_page_config(page_title="AI Accounting — Kafe", page_icon="🧾", layout="wide")
st.markdown("<style>.badge{padding:3px 10px;border-radius:12px;font-weight:600}.mono{font-family:monospace}</style>", unsafe_allow_html=True)


def rp(value) -> str:
    try:
        return f"Rp {Decimal(str(value)):,.0f}".replace(",", ".")
    except Exception:
        return "Rp 0"


def db_check():
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return True, ""
    except Exception as exc:
        return False, str(exc)


def load_samples():
    result = {}
    for path in sorted(SAMPLE_DIR.glob("*.json")) if SAMPLE_DIR.exists() else []:
        try:
            result[path.name] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return result


def render_detail(draft: dict):
    icon, color = BADGE.get(draft["status"], ("❓", "#eee"))
    st.markdown(f"### {draft['draft_no']} <span class='badge' style='background:{color}'>{icon} {draft['status']}</span>", unsafe_allow_html=True)
    st.caption(f"Invoice **{draft['external_id']}** · tanggal **{draft['business_date']}** · engine `{draft.get('ai_model')}` · confidence `{draft.get('confidence')}`")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Debit", rp(draft["total_debit"]))
    c2.metric("Total Kredit", rp(draft["total_credit"]))
    balanced = Decimal(str(draft["total_debit"])) == Decimal(str(draft["total_credit"]))
    c3.metric("Balance", "SEIMBANG ✅" if balanced else "TIDAK SEIMBANG ⚠️")
    items = draft.get("items") or []
    if items:
        frame = pd.DataFrame(items)[["line_no", "account_code", "account_name", "debit", "credit", "description"]]
        frame.columns = ["#", "Kode", "Nama Akun", "Debit", "Kredit", "Keterangan"]
        frame["Debit"] = frame["Debit"].apply(rp)
        frame["Kredit"] = frame["Kredit"].apply(rp)
        st.markdown("#### Baris Jurnal")
        st.dataframe(frame, hide_index=True, width="stretch")
    with st.expander("🧠 Alasan mapping"):
        st.write(draft.get("ai_reasoning") or "—")
        st.json(draft.get("payload") or {})
    if draft["status"] == "PENDING":
        a, b, c, _ = st.columns([1, 1, 1, 3])
        if a.button("✅ Approve", key=f"ap{draft['id']}", type="primary"):
            set_draft_status(draft["id"], "APPROVED", REVIEWER)
            st.rerun()
        if b.button("❌ Reject", key=f"rj{draft['id']}"):
            set_draft_status(draft["id"], "REJECTED", REVIEWER)
            st.rerun()
        if c.button("🔁 Recompute", key=f"rc{draft['id']}"):
            info = recompute_draft(draft["id"])
            st.success(f"Recompute: {info['items']} baris, {rp(info['total_debit'])}")
            st.rerun()
    elif st.button("↩️ Balikin ke PENDING", key=f"bk{draft['id']}"):
        set_draft_status(draft["id"], "PENDING", REVIEWER)
        st.rerun()


def page_drafts():
    picked = st.radio("Filter status", ["Semua", "PENDING", "APPROVED", "REJECTED", "SYNCED"], horizontal=True, label_visibility="collapsed")
    rows = list_drafts(None if picked == "Semua" else picked, 500)
    if not rows:
        st.info("Belum ada draft. Buka tab Demo & Utils untuk load contoh.")
        return
    frame = pd.DataFrame([{"id": r["id"], "Draft": r["draft_no"], "Invoice": r["external_id"], "Tanggal": str(r["business_date"]), "Status": r["status"], "Nilai": rp(r["total_debit"]), "Baris": len(r.get("items") or []), "Reviewer": r["reviewed_by"] or "-"} for r in rows])
    st.metric("Jumlah draft", len(rows))
    st.dataframe(frame.drop(columns=["id"]), hide_index=True, width="stretch")
    choices = {f"{r['draft_no']} · {r['external_id']} · {rp(r['total_debit'])}": r["id"] for r in rows}
    choice = st.selectbox("Pilih draft untuk direview", list(choices))
    if choice:
        detail = next(r for r in rows if r["id"] == choices[choice])
        render_detail(detail)


def page_coa():
    rows = list_coa_rows()
    frame = pd.DataFrame(rows)
    if frame.empty:
        st.warning("COA kosong. Jalankan python sql/create_db.py")
        return
    frame["Aktif"] = frame["is_active"].map({True: "✅", False: "—"})
    st.dataframe(frame[["account_code", "account_name", "account_type", "normal_balance", "Aktif", "description"]], hide_index=True, width="stretch")
    st.caption("COA masih dummy; nanti ganti sql/002_seed_coa.sql dengan COA Accurate asli.")
    with st.expander("Mapping rules aktif"):
        st.code("CASH → D 1100 Kas\nQRIS → D 1120 Settlement QRIS\nDEBIT/EDC → D 1121 Settlement EDC\nMDR → D 6100 Beban MDR\nDPP → K 4100 Pendapatan Penjualan\nService → K 4110 Pendapatan Service Charge\nPB1 → K 2100 Utang Pajak PB1")


def page_utils():
    st.markdown("#### Load contoh transaksi")
    for name, payload in load_samples().items():
        left, right = st.columns([3, 1])
        left.write(f"`{name}`")
        if right.button("Ingest", key=f"sample-{name}"):
            try:
                raw_id, draft_id = ingest_transaction(payload)
                st.success(f"Masuk: raw_id={raw_id}, draft_id={draft_id}")
                st.rerun()
            except (ValueError, MappingError) as exc:
                st.error(f"Gagal: {exc}")
    st.markdown("---")
    st.markdown("#### Upload JSON manual")
    uploaded = st.file_uploader("File JSON transaksi Accurate POS", type=["json"])
    if uploaded and st.button("Ingest upload"):
        try:
            raw_id, draft_id = ingest_transaction(json.loads(uploaded.read().decode("utf-8")))
            st.success(f"Masuk: raw_id={raw_id}, draft_id={draft_id}")
            st.rerun()
        except (ValueError, MappingError, json.JSONDecodeError) as exc:
            st.error(f"Gagal: {exc}")
    st.markdown("---")
    st.markdown("#### Kalkulator manual (tidak disimpan)")
    with st.form("calculator"):
        c1, c2, c3 = st.columns(3)
        qty = c1.number_input("Qty", 1, 999, 1)
        price = c2.number_input("Harga satuan", 0, 100_000_000, 50000, step=1000)
        discount = c3.number_input("Diskon bill", 0, 100_000_000, 0, step=1000)
        c4, c5 = st.columns(2)
        pb1 = c4.number_input("PB1 (%)", 0.0, 30.0, 10.0, step=0.5)
        service = c5.number_input("Service charge (%)", 0.0, 30.0, 0.0, step=0.5)
        method = st.selectbox("Metode bayar", ["CASH", "QRIS", "DEBIT"])
        run = st.form_submit_button("Hitung", type="primary")
    if run:
        payload = {"invoice_no": f"SIM-{uuid.uuid4().hex[:6].upper()}", "business_date": "2026-11-02", "tax": {"pb1_rate": pb1 / 100, "service_charge_rate": service / 100, "tax_inclusive": False}, "lines": [{"item_name": "Simulasi", "qty": int(qty), "unit_price": price}], "bill_discount": discount, "payments": [{"method": "CASH", "gross_amount": 10**12, "mdr_rate": 0.0}]}
        result = calculate(payload)
        st.dataframe(pd.DataFrame([["DPP", rp(result.dpp)], ["Service charge", rp(result.service_charge)], ["PB1", rp(result.tax)], ["TOTAL", rp(result.total_due)], ["Kembalian", rp(result.change_due)]], columns=["Komponen", "Nilai"]), hide_index=True, width="stretch")
    st.markdown("---")
    st.markdown("#### Push ke Google Drive")
    st.caption("Excel mingguan berisi draft APPROVED 7 hari terakhir. Upload manual ini memakai folder `AI Accounting Reports`.")
    try:
        from app.drive_export import export_to_drive, gdrive_available
        drive_ok = gdrive_available()
    except Exception:
        drive_ok = False

    if drive_ok:
        if st.button("📤 Push APPROVED 7 hari terakhir ke GDrive"):
            try:
                result = export_to_drive(since_days=7, only_approved=True)
                if result.get("status") == "uploaded":
                    st.success(f"✅ {result['draft_count']} draft berhasil di-push ke GDrive")
                    st.link_button("🔗 Buka file Excel", result["web_view_link"])
                else:
                    st.info(result.get("message", "Tidak ada data untuk di-push."))
            except Exception as exc:  # noqa: BLE001
                st.error(f"❌ Push GDrive gagal: {exc}")
    else:
        st.info(
            "Push GDrive manual hanya jalan di **mesin lokal** (butuh `google_api.py` + "
            "token OAuth Google). Di Streamlit Cloud button ini disembunyikan, tapi "
            "**ekspor mingguan otomatis tetap jalan** lewat cron lokal setiap Minggu 09:00 WIB — "
            "file Excel mendarat di folder `AI Accounting Reports`."
        )

    st.markdown("---")
    st.warning("Danger zone: hapus semua transaksi & draft (COA tetap).")
    if st.checkbox("Saya yakin") and st.button("🗑️ Hapus semua data"):
        reset_all()
        st.success("Semua data dihapus.")
        st.rerun()


def main():
    require_login()
    ok, error = db_check()
    if not ok:
        st.error("❌ Tidak bisa connect ke database")
        st.code(error)
        st.info("Cek Postgres / DATABASE_URL (di `.env` lokal atau Streamlit Cloud → Secrets), lalu jalankan `python sql/create_db.py` untuk setup awal.")
        st.stop()
    stats = get_stats()
    st.title("🧾 AI Accounting — Dashboard Review Jurnal")
    st.caption(f"Deterministic rules engine · DB `{db_label()}`")
    cols = st.columns(6)
    cols[0].metric("Raw transaksi", stats["raw_transactions"])
    cols[1].metric("⏳ Pending", stats["pending"])
    cols[2].metric("✅ Approved", stats["approved"])
    cols[3].metric("❌ Rejected", stats["rejected"])
    cols[4].metric("🔄 Synced", stats["synced"])
    cols[5].metric("Turnover", rp(stats["turnover"]))
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["📋 Review Draft", "📚 COA", "🛠 Demo & Utils"])
    with tab1:
        page_drafts()
    with tab2:
        page_coa()
    with tab3:
        page_utils()
    st.sidebar.markdown("### Accurate Online")
    st.sidebar.warning("⛔ Push belum aktif — API Accurate Online belum diberikan.")
    st.sidebar.button("🚀 Push ke Accurate Online", disabled=True, width="stretch")
    st.sidebar.caption("Engine: rules-engine-v1 · Reviewer: nizar")


main()
