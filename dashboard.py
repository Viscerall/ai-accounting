"""Dawend — Streamlit dashboard.

Design: taste-skill app screen, style "accent-ladder" (light), shell "ruled-t-frame".
One brand hue (#b8336a) at full strength only on small marks; its pale tints carry
every area (active nav row, selected queue row, pills, focus rings).
"""
from __future__ import annotations

import json
import os
import traceback
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Dawend · Accounting Dashboard",
    page_icon="◧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── imports (fail closed, show the traceback) ───────────────────────────────
try:
    from app.calculator import calculate
    from app.auth import check_password, logout, require_login
    from app.config import db_label
    from app.db import (
        branch_usage,
        create_branch,
        delete_branch,
        get_conn,
        get_stats,
        ingest_transaction,
        list_branches,
        list_coa_rows,
        list_drafts,
        recompute_draft,
        reset_all,
        set_draft_status,
        update_branch,
    )
    from app.mapping_rules import MappingError
except Exception:  # noqa: BLE001
    _tb = traceback.format_exc()
    st.title("Import gagal")
    st.error("Modul `app` gagal diimpor. Kirim teks di bawah ke developer.")
    st.code(_tb, language="python")
    st.stop()

SAMPLE_DIR = Path(__file__).parent / "data" / "samples"
REVIEWER = "Tim Dawend"


# ── helpers ─────────────────────────────────────────────────────────────────
def rp(value) -> str:
    try:
        n = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return "Rp 0"
    return f"Rp {n:,.0f}".replace(",", ".")


def num(value) -> str:
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def db_check() -> tuple[bool, str]:
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def load_samples() -> dict:
    out = {}
    if SAMPLE_DIR.exists():
        for path in sorted(SAMPLE_DIR.glob("*.json")):
            try:
                out[path.name] = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
    return out


PILL = {
    "PENDING": ("Menunggu", "pill-accent"),
    "APPROVED": ("Disetujui", "pill-positive"),
    "REJECTED": ("Ditolak", "pill-negative"),
    "SYNCED": ("Tersinkron", "pill-neutral"),
}


def pill(status: str) -> str:
    label, cls = PILL.get(status, (status, "pill-neutral"))
    return f'<span class="pill {cls}">{label}</span>'


def friendly(exc: Exception) -> str:
    text = str(exc)
    low = text.lower()
    if "duplicate key" in low or "unique constraint" in low:
        return "Kode cabang itu sudah dipakai. Pilih kode lain."
    if "foreign key" in low:
        return "Cabang ini masih dipakai data lain, jadi tidak bisa dihapus."
    return text


def radio_default(key: str, options: list, default):
    if key not in st.session_state or st.session_state[key] not in options:
        st.session_state[key] = default


def _set_page(source_key: str) -> None:
    """Keep the desktop sidebar nav and the mobile top nav in sync."""
    page = st.session_state.get(source_key)
    if page is None:
        return
    st.session_state["page"] = page
    other = "nav_mobile" if source_key == "nav_radio" else "nav_radio"
    if st.session_state.get(other) != page:
        st.session_state[other] = page


# ── CSS ─────────────────────────────────────────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&display=swap');

:root{
  --ground:#fbf7f8; --surface:#ffffff; --raised:#f3f4f6; --border:#e5e7eb;
  --rule:#f2f2f2; --control:#d1d5db; --text:#111827; --muted:#5f6672;
  --accent:#b8336a; --accent-soft:#fdf2f7; --accent-track:#f8dbe8; --accent-ink:#6b1d3e;
  --positive:#247b50; --negative:#c4242a; --warning:#92400e;
  --r-card:8px; --r-ctl:6px; --row:45px; --gap:24px; --pad:24px; --ctl-h:32px;
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"]{
  font-family:"DM Sans", Inter, system-ui, sans-serif;
  -webkit-font-smoothing:antialiased;
}
[data-testid="stAppViewContainer"]{ background:var(--ground); color:var(--text); }
#MainMenu, footer{ display:none !important; }
[data-testid="stToolbar"]{ display:none !important; }
[data-testid="stDecoration"]{ display:none !important; }
[data-testid="stStatusWidget"]{ display:none !important; }
/* The app header also hosts the sidebar toggle. Hide it on desktop only —
   on phones it is the only way to open the menu. */
@media (min-width:901px){
  header[data-testid="stHeader"]{ display:none !important; }
}
@media (max-width:900px){
  header[data-testid="stHeader"]{
    display:block !important; background:transparent !important;
    box-shadow:none !important; height:auto !important;
  }
  [data-testid="stSidebarCollapsedControl"]{ display:flex !important; visibility:visible !important; }
  [data-testid="stSidebarCollapsedControl"] button{ color:var(--accent) !important; }
}

/* ── frame: no global padding, we pad ourselves ── */
[data-testid="stMain"] .block-container,
[data-testid="stAppViewContainer"] .block-container{
  padding:0 !important; max-width:100% !important;
}
[data-testid="stSidebar"]{ background:var(--ground) !important; border-right:1px solid var(--rule); }
[data-testid="stSidebar"] > div{ background:transparent; }
[data-testid="stSidebarUserContent"]{ padding:22px 14px 18px !important; }
[data-testid="stSidebarCollapseButton"] button{ color:var(--muted) !important; }

/* ── type ── */
h1,h2,h3,h4,h5{ font-family:"DM Sans",sans-serif; color:var(--text); letter-spacing:-0.01em; }
p, span, div, label, li{ font-size:14px; }
code, .mono{ font-variant-numeric:tabular-nums; }

/* ── sidebar brand ── */
.brand{ display:flex; align-items:center; gap:9px; margin:2px 0 26px 2px; }
.brand .mark{
  width:26px; height:26px; border-radius:7px; background:var(--accent);
  color:#fff; font-weight:700; font-size:13px; display:flex;
  align-items:center; justify-content:center; flex:0 0 auto;
}
.brand .name{ font-weight:700; font-size:15px; line-height:1.1; letter-spacing:-0.015em; }
.brand .scope{ font-size:12px; color:var(--muted); line-height:1.3; }

.nav-label{ font-size:12px; color:var(--muted); margin:0 0 6px 10px; }

/* ── sidebar nav radio → nav rows ── */
.st-key-nav_radio [data-testid="stRadio"] > label{ display:none; }
.st-key-nav_radio [role="radiogroup"]{ gap:1px; display:flex; flex-direction:column; }
.st-key-nav_radio label[data-baseweb="radio"]{
  height:38px; padding:0 10px; border-radius:var(--r-ctl);
  display:flex; align-items:center; gap:0; cursor:pointer;
  transition:background .12s ease, color .12s ease; margin:0;
}
.st-key-nav_radio label[data-baseweb="radio"] > div:first-child{ display:none !important; }
.st-key-nav_radio label[data-baseweb="radio"] p,
.st-key-nav_radio label[data-baseweb="radio"] div[data-testid="stMarkdownContainer"] p{
  font-size:14px; font-weight:400; color:var(--text); margin:0;
}
.st-key-nav_radio label[data-baseweb="radio"]:hover{ background:var(--raised); }
.st-key-nav_radio label[data-baseweb="radio"]:has(input:checked){ background:var(--accent-soft); }
.st-key-nav_radio label[data-baseweb="radio"]:has(input:checked) p{
  color:var(--accent-ink); font-weight:500;
}

/* ── sidebar footer ── */
.side-foot{ margin-top:22px; padding-top:14px; border-top:1px solid var(--rule); }
.side-foot .kv{ display:flex; justify-content:space-between; gap:12px; font-size:12px; line-height:1.9; }
.side-foot .k{ color:var(--muted); flex:0 0 auto; }
.side-foot .v{
  color:var(--text); text-align:right; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap;
}
.side-foot .dot{ color:var(--positive); }

[data-testid="stSidebar"] .stButton button{
  width:100%; justify-content:flex-start; height:32px; padding:0 10px;
  background:transparent; border:1px solid var(--border); border-radius:var(--r-ctl);
  color:var(--muted); font-size:13px; font-weight:400; box-shadow:none;
}
[data-testid="stSidebar"] .stButton button:hover{
  background:var(--surface); border-color:var(--control); color:var(--text);
}

/* ── top bar ── */
.st-key-topbar{ border-bottom:1px solid var(--rule); padding:0 var(--pad) !important; }
.st-key-topbar [data-testid="stHorizontalBlock"]{ height:64px; align-items:center; }
.tb-title{ font-size:17px; font-weight:500; letter-spacing:-0.01em; line-height:1.2; }
.tb-sub{ font-size:12px; color:var(--muted); line-height:1.3; margin-top:1px; }
.tb-sep{ border-left:1px solid var(--rule); height:32px; }
.st-key-topbar .stSelectbox{ max-width:280px; margin-left:auto; }
.st-key-topbar .stSelectbox label{ display:none; }

/* ── content ── */
.st-key-content{ padding:22px var(--pad) 40px !important; }

/* ── KPI container: one panel, equal cells, 1px dividers ── */
.kpis{
  display:grid; grid-template-columns:repeat(4, minmax(0,1fr));
  background:var(--surface); border:1px solid var(--border);
  border-radius:var(--r-card); overflow:hidden; margin:0 0 22px;
}
.kpi{
  display:flex; flex-direction:column; justify-content:center;
  padding:14px 18px 15px; border-right:1px solid var(--rule); min-width:0;
}
.kpi:last-child{ border-right:0; }
.kpi .lab{ font-size:12px; color:var(--muted); margin-bottom:5px; line-height:1.35; }
.kpi .val{
  font-size:24px; font-weight:500; letter-spacing:-0.02em;
  font-variant-numeric:tabular-nums; line-height:1.15;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
.kpi .val.hue{ color:var(--accent); }
.kpi .cap{ font-size:12px; color:var(--muted); margin-top:4px; line-height:1.35; }

/* ── status tabs (underline, 2px indicator) ── */
.st-key-status_tabs [data-testid="stRadio"] > label{ display:none; }
.st-key-status_tabs [role="radiogroup"]{
  border-bottom:1px solid var(--rule); gap:0; padding:0;
}
.st-key-status_tabs label[data-baseweb="radio"]{
  padding:0 0 9px; margin:0 22px 0 0; border-radius:0; position:relative;
  background:transparent !important; cursor:pointer;
}
.st-key-status_tabs label[data-baseweb="radio"] > div:first-child{ display:none !important; }
.st-key-status_tabs label[data-baseweb="radio"] p{
  font-size:13px; font-weight:400; color:var(--muted); margin:0;
}
.st-key-status_tabs label[data-baseweb="radio"]:hover p{ color:var(--text); }
.st-key-status_tabs label[data-baseweb="radio"]:has(input:checked) p{
  color:var(--text); font-weight:500;
}
.st-key-status_tabs label[data-baseweb="radio"]:has(input:checked)::after{
  content:""; position:absolute; left:0; right:0; bottom:-1px;
  height:2px; background:var(--accent); border-radius:2px 2px 0 0;
}

/* ── queue rail ── */
.st-key-rail{ background:var(--surface); border:1px solid var(--border);
  border-radius:var(--r-card); overflow:hidden; }
.rail-head{ padding:11px 14px; border-bottom:1px solid var(--rule);
  display:flex; justify-content:space-between; align-items:baseline; }
.rail-head .t{ font-size:13px; font-weight:500; }
.rail-head .c{ font-size:12px; color:var(--muted); }

.st-key-rail_radio [data-testid="stRadio"] > label{ display:none; }
.st-key-rail_radio [role="radiogroup"]{ gap:0; display:flex; flex-direction:column; }
.st-key-rail_radio label[data-baseweb="radio"]{
  min-height:var(--row); padding:8px 14px; border-radius:0; margin:0;
  border-bottom:1px solid var(--rule); display:flex; align-items:center;
  cursor:pointer; transition:background .12s ease; background:transparent;
}
.st-key-rail_radio label[data-baseweb="radio"]:last-child{ border-bottom:0; }
.st-key-rail_radio label[data-baseweb="radio"] > div:first-child{ display:none !important; }
.st-key-rail_radio label[data-baseweb="radio"] p{
  font-size:13px; font-weight:400; color:var(--text); margin:0;
  font-variant-numeric:tabular-nums; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis;
}
.st-key-rail_radio label[data-baseweb="radio"]:hover{ background:var(--raised); }
.st-key-rail_radio label[data-baseweb="radio"]:has(input:checked){ background:var(--accent-soft); }
.st-key-rail_radio label[data-baseweb="radio"]:has(input:checked) p{
  color:var(--accent-ink); font-weight:500;
}

.rail-empty{ padding:34px 18px; text-align:center; color:var(--muted); font-size:13px; line-height:1.6; }

/* ── detail ── */
.st-key-detail{ padding-top:2px; }
.d-head .row1{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.d-head .no{ font-size:17px; font-weight:500; letter-spacing:-0.01em; }
.d-head .meta{ font-size:12px; color:var(--muted); margin-top:5px; line-height:1.7; }
.d-head .meta b{ color:var(--text); font-weight:500; }
.d-head .amt{ font-size:30px; font-weight:500; letter-spacing:-0.03em;
  color:var(--accent); font-variant-numeric:tabular-nums; margin-top:12px; line-height:1; }

.pill{ display:inline-block; padding:3px 9px; border-radius:999px;
  font-size:11px; font-weight:500; line-height:1.35; white-space:nowrap; }
.pill-positive{ background:#dcfce7; color:#14532d; }
.pill-negative{ background:#ffedea; color:#831c1e; }
.pill-warning{ background:#fffbeb; color:#92400e; }
.pill-neutral{ background:#f3f4f6; color:#374151; }
.pill-accent{ background:var(--accent-soft); color:var(--accent-ink); }

/* ── tables: no card, no fill on header ── */
table.jt, table.plain{ width:100%; border-collapse:collapse; }
table.jt th, table.plain th{
  font-size:12px; font-weight:400; color:var(--muted); text-align:left;
  padding:10px 12px; border-bottom:1px solid var(--border); background:transparent;
  white-space:nowrap;
}
table.jt td, table.plain td{
  font-size:13px; padding:10px 12px; border-bottom:1px solid var(--rule);
  vertical-align:middle;
}
table.jt tr:last-child td, table.plain tr:last-child td{ border-bottom:0; }
table.jt td.n, table.plain td.n, table.jt th.n, table.plain th.n{
  text-align:right; font-variant-numeric:tabular-nums;
}
table.jt td.n{ font-weight:500; }
table.jt tbody tr:hover td{ background:var(--ground); }
table.jt tfoot td{
  font-size:13px; font-weight:500; padding:11px 12px;
  border-top:1px solid var(--border); border-bottom:0; background:var(--surface);
}
table.jt tfoot td:first-child{ color:var(--muted); font-weight:400; }
.wrap{ width:100%; overflow-x:auto; -webkit-overflow-scrolling:touch; }
.wrap table.jt, .wrap table.plain{ min-width:640px; }
.jt-wrap{ width:100%; overflow-x:auto; margin-top:16px; -webkit-overflow-scrolling:touch; }
.jt-wrap table.jt{ min-width:640px; }
table.jt td.desc{ color:var(--muted); white-space:normal; min-width:210px; }
table.plain td.muted, table.jt td.muted{ color:var(--muted); }
.table-cap{
  font-size:12px; color:var(--muted); display:flex; justify-content:space-between;
  align-items:baseline; gap:12px; margin:0 0 8px;
}

/* totals strip above the table: always visible, no scrolling needed */
.totals{
  display:flex; flex-wrap:wrap; gap:0; margin:18px 0 2px;
  background:var(--surface); border:1px solid var(--border); border-radius:var(--r-card);
  overflow:hidden;
}
.totals .cell{ flex:1 1 0; min-width:150px; padding:12px 16px; border-right:1px solid var(--rule); }
.totals .cell:last-child{ border-right:0; }
.totals .lab{ font-size:12px; color:var(--muted); margin-bottom:4px; }
.totals .val{ font-size:18px; font-weight:500; font-variant-numeric:tabular-nums; letter-spacing:-0.01em; }
.totals .state{ display:flex; align-items:center; gap:8px; }
table.plain td.code{ font-weight:500; font-variant-numeric:tabular-nums; }

/* responsive: table on desktop, cards on mobile */
.only-desktop{ display:block; }
.only-mobile{ display:none; }
@media (max-width:760px){
  .only-desktop{ display:none; }
  .only-mobile{ display:block; }
  .jt-wrap{ display:none; }
  .jt-items .it{
    display:grid; grid-template-columns:1fr 1fr; gap:6px 12px;
    padding:10px 12px; border:1px solid var(--border); border-radius:var(--r-card);
    background:var(--surface); margin-bottom:8px; align-items:center;
  }
  .jt-items .it > div:first-child{ grid-column:1 / -1; }
  .jt-items .code{ font-weight:500; font-size:13px; color:var(--text); }
  .jt-items .name{ font-size:12px; color:var(--muted); }
  .jt-items .dr, .jt-items .cr{ display:flex; justify-content:space-between; gap:8px; }
  .jt-items .dr .lab, .jt-items .cr .lab{ font-size:11px; color:var(--muted); }
  .jt-items .dr .val, .jt-items .cr .val{
    font-size:13px; font-weight:500; font-variant-numeric:tabular-nums;
  }
  .jt-items .cr .val{ color:var(--negative); }
  .jt-items .desc{ grid-column:1 / -1; font-size:12px; color:var(--muted); }
}

/* ── panels for forms / secondary blocks ── */
.panel{ background:var(--surface); border:1px solid var(--border);
  border-radius:var(--r-card); padding:18px 20px; margin-bottom:16px; }
.panel h4{ font-size:14px; font-weight:500; margin:0 0 12px; letter-spacing:-0.005em; }
.panel .hint{ font-size:12px; color:var(--muted); margin:-4px 0 12px; }

/* ── form controls ── */
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input{
  height:var(--ctl-h) !important; border-radius:var(--r-ctl) !important;
  border-color:var(--border) !important; font-size:13px !important;
  background:var(--surface) !important; color:var(--text) !important;
}
[data-testid="stTextInput"] input:focus, [data-testid="stNumberInput"] input:focus{
  border-color:var(--accent) !important; box-shadow:0 0 0 3px var(--accent-soft) !important;
}
[data-baseweb="select"] > div{
  height:var(--ctl-h) !important; min-height:var(--ctl-h) !important;
  border-radius:var(--r-ctl) !important; border-color:var(--border) !important;
  background:var(--surface) !important; font-size:13px !important;
}
[data-baseweb="select"]:focus-within > div{
  border-color:var(--accent) !important; box-shadow:0 0 0 3px var(--accent-soft) !important;
}
[data-testid="stWidgetLabel"] label, .stTextInput label, .stSelectbox label, .stNumberInput label{
  font-size:12px !important; color:var(--muted) !important; font-weight:400 !important;
}

/* ── buttons ── */
.stButton button, .stFormSubmitButton button, [data-testid="stLinkButton"] a{
  height:32px; padding:0 14px; border-radius:var(--r-ctl);
  font-size:13px; font-weight:500; box-shadow:none; transition:all .12s ease;
}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"]{
  background:var(--accent); border:1px solid var(--accent); color:#fff;
}
.stButton button[kind="primary"]:hover, .stFormSubmitButton button[kind="primary"]:hover{
  background:var(--accent-ink); border-color:var(--accent-ink); color:#fff;
}
.stButton button[kind="secondary"], .stFormSubmitButton button[kind="secondary"]{
  background:var(--surface); border:1px solid var(--border); color:var(--text);
}
.stButton button[kind="secondary"]:hover{
  background:var(--raised); border-color:var(--control);
}
.stButton button[kind="tertiary"]{
  background:transparent; border:1px solid transparent; color:var(--muted);
}
.stButton button[kind="tertiary"]:hover{ color:var(--text); background:var(--raised); }
.stButton button:focus-visible, .stFormSubmitButton button:focus-visible{
  outline:2px solid var(--accent); outline-offset:2px;
}

/* ── expander / captions / alerts ── */
[data-testid="stExpander"] details{
  border:1px solid var(--border); border-radius:var(--r-card);
  background:var(--surface); overflow:hidden;
}
[data-testid="stExpander"] summary{ padding:11px 16px; font-size:13px; font-weight:400; }
[data-testid="stExpander"] summary:hover{ background:var(--ground); }
[data-testid="stExpander"] [data-testid="stExpanderDetails"]{ padding:0 16px 14px; }

[data-testid="stCaptionContainer"] p, .stCaption p{ font-size:12px !important; color:var(--muted) !important; }
[data-testid="stAlert"]{ border-radius:var(--r-card); font-size:13px; }

/* ── login ── */
.st-key-login{ max-width:372px; margin:14vh auto 0; }
.st-key-login .brand{ margin-bottom:18px; }
.login-h{ font-size:22px; font-weight:500; letter-spacing:-0.02em; margin:0 0 6px; }
.login-p{ font-size:13px; color:var(--muted); margin:0 0 20px; line-height:1.6; }
.login-f{ font-size:12px; color:var(--muted); margin-top:18px; line-height:1.6; }

/* ── mobile top nav (phones only): mirrors the sidebar menu ── */
.st-key-nav_mobile_wrap{ display:none; }
.st-key-nav_mobile_foot{ display:none; }
@media (max-width:900px){
  .st-key-nav_mobile_wrap{ display:block; padding:0 12px !important; }
  .st-key-nav_mobile_foot{ display:block; padding:0 12px !important; }
  .mfoot{ font-size:11px; color:var(--muted); line-height:1.5; padding:2px 0; }
  .mfoot b{ color:var(--text); font-weight:500; }
  .st-key-nav_mobile_foot .stButton button{
    height:28px; font-size:12px; background:var(--surface);
    border:1px solid var(--border); color:var(--muted);
  }
  .st-key-nav_mobile_wrap [data-testid="stRadio"] > label{ display:none; }
  .st-key-nav_mobile_wrap [role="radiogroup"]{
    display:flex; gap:6px; overflow-x:auto; scrollbar-width:none;
    padding:10px 0 10px; margin:0; border-bottom:1px solid var(--rule);
  }
  .st-key-nav_mobile_wrap [role="radiogroup"]::-webkit-scrollbar{ display:none; }
  .st-key-nav_mobile_wrap label[data-baseweb="radio"]{
    flex:0 0 auto; height:32px; padding:0 12px; margin:0; border-radius:999px;
    background:var(--surface) !important; border:1px solid var(--border);
    display:flex; align-items:center; cursor:pointer;
  }
  .st-key-nav_mobile_wrap label[data-baseweb="radio"] > div:first-child{ display:none !important; }
  .st-key-nav_mobile_wrap label[data-baseweb="radio"] p{ font-size:13px; color:var(--text); margin:0; }
  .st-key-nav_mobile_wrap label[data-baseweb="radio"]:has(input:checked){
    background:var(--accent-soft) !important; border-color:var(--accent-track);
  }
  .st-key-nav_mobile_wrap label[data-baseweb="radio"]:has(input:checked) p{
    color:var(--accent-ink); font-weight:500;
  }
  /* sidebar menu stays desktop-only; phones use the pill nav above */
  [data-testid="stSidebar"] .st-key-nav_radio{ display:none; }
  .st-key-login{ max-width:100%; margin:6vh auto 0; padding:0 4px !important; }
}

/* ── phone ── */
@media (max-width:900px){
  .kpis{ grid-template-columns:repeat(2, minmax(0,1fr)); margin-bottom:18px; }
  .kpi{ padding:12px 13px; min-height:88px; border-bottom:1px solid var(--rule); }
  .kpi:nth-child(2n){ border-right:0; }
  .kpi:nth-child(n+3){ border-bottom:0; }
  .kpi .val{ font-size:20px; }
  .kpi .cap{ font-size:11px; }
  .st-key-content{ padding:14px 12px 28px !important; }
  .st-key-topbar{ padding:0 12px !important; }
  .st-key-topbar [data-testid="stHorizontalBlock"]{ height:auto; padding:8px 0 10px; gap:8px; }
  .st-key-topbar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child{ min-width:0; }
  .st-key-topbar .tb-title{ font-size:16px; }
  .st-key-topbar .tb-sub{ font-size:11px; }
  .st-key-topbar .stSelectbox{ min-width:0; }
  .st-key-topbar [data-baseweb="select"] > div{ max-width:145px; }
  .st-key-status_tabs [role="radiogroup"]{ overflow-x:auto; scrollbar-width:none; }
  .st-key-status_tabs label[data-baseweb="radio"]{ flex:0 0 auto; margin-right:18px; }
  .st-key-rail{ margin-bottom:16px; }
  .st-key-rail_radio label[data-baseweb="radio"]{ min-height:42px; }
  .totals .cell{ min-width:50%; padding:11px 12px; }
  .totals .cell:nth-child(2){ border-right:0; }
  .totals .cell:nth-child(1), .totals .cell:nth-child(2){ border-bottom:1px solid var(--rule); }
  .totals .val{ font-size:16px; }
  .jt-wrap{ margin-top:12px; }
  .d-head .amt{ font-size:25px; }
  .d-head .meta{ font-size:11px; line-height:1.6; }
  .st-key-detail .stButton button{ width:100%; }
}
"""


def inject_css() -> None:
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


# ── sidebar ─────────────────────────────────────────────────────────────────
NAV = [
    ("review", "Review jurnal"),
    ("coa", "Buku besar"),
    ("branches", "Cabang"),
    ("utils", "Alat & demo"),
]


def render_sidebar(reviewer: str = "Tim Dawend") -> str:
    with st.sidebar:
        st.markdown(
            '<div class="brand"><div class="mark">D</div>'
            '<div><div class="name">Dawend</div>'
            '<div class="scope">Accounting Dashboard</div></div></div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="nav-label">Menu</div>', unsafe_allow_html=True)
        keys = [k for k, _ in NAV]
        labels = [lbl for _, lbl in NAV]
        radio_default("nav_radio", keys, keys[0])
        st.radio(
            "Menu",
            keys,
            format_func=lambda k: labels[keys.index(k)],
            key="nav_radio",
            label_visibility="collapsed",
            width="stretch",
            on_change=_set_page,
            args=("nav_radio",),
        )
        active = st.session_state.get("page", st.session_state.get("nav_radio", keys[0]))

        # Sidebar is the canonical desktop navigation; mobile gets a compact
        # duplicate rendered in the main content area below.
        st.session_state["page"] = active

        st.markdown('<div class="side-foot">', unsafe_allow_html=True)
        st.markdown(
            '<div class="kv"><span class="k">Engine</span><span class="v">rules-engine-v1</span></div>'
            '<div class="kv"><span class="k">Reviewer</span><span class="v">' + reviewer + '</span></div>'
            f'<div class="kv"><span class="k">Database</span><span class="v">{db_label()}</span></div>'
            '<div class="kv"><span class="k">Accurate</span><span class="v">belum aktif</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        if st.button("Keluar", key="logout", icon=":material/logout:"):
            logout()
            st.rerun()

    return active


# ── top bar ─────────────────────────────────────────────────────────────────
def render_mobile_nav(reviewer: str = "Tim Dawend") -> None:
    """Compact nav for phones — the sidebar is hidden by CSS under 900px."""
    keys = [k for k, _ in NAV]
    labels = dict(NAV)
    radio_default("nav_mobile", keys, st.session_state.get("page", keys[0]))

    with st.container(key="nav_mobile_wrap"):
        st.radio(
            "Menu",
            keys,
            format_func=lambda k: labels[k],
            key="nav_mobile",
            horizontal=True,
            label_visibility="collapsed",
            on_change=_set_page,
            args=("nav_mobile",),
        )

    with st.container(key="nav_mobile_foot"):
        left, right = st.columns([3, 1], vertical_alignment="center")
        with left:
            st.markdown(
                f'<div class="mfoot">Reviewer <b>{reviewer}</b>'
                f' &nbsp;·&nbsp; DB <b>{db_label()}</b></div>',
                unsafe_allow_html=True,
            )
        with right:
            if st.button("Keluar", key="logout_m", width="stretch"):
                logout()
                st.rerun()


TITLES = {
    "review": ("Review jurnal", "Draft jurnal harian yang menunggu keputusan"),
    "coa": ("Buku besar", "Chart of accounts yang dipakai mapping"),
    "branches": ("Cabang", "Kelola kode, nama, dan status cabang"),
    "utils": ("Alat & demo", "Seed contoh, upload JSON, kalkulator, ekspor"),
}


def render_topbar(page: str, branches: list, current: str | None) -> str | None:
    title, sub = TITLES[page]
    opts: dict[str, str | None] = {"Semua cabang": None}
    for b in branches:
        label = f"{b['branch_code']} · {b['branch_name']}"
        if b["city"]:
            label += f", {b['city']}"
        opts[label] = b["branch_code"]

    labels = list(opts)
    resolved = next((l for l in labels if opts[l] == current), "Semua cabang")
    radio_default("branch_sel", labels, resolved)

    with st.container(key="topbar"):
        left, right = st.columns([2.2, 1], vertical_alignment="center")
        with left:
            st.markdown(
                f'<div class="tb-title">{title}</div><div class="tb-sub">{sub}</div>',
                unsafe_allow_html=True,
            )
        with right:
            picked = st.selectbox(
                "Cabang", labels, key="branch_sel", label_visibility="collapsed"
            )
    return opts.get(picked)


# ── KPI ─────────────────────────────────────────────────────────────────────
def render_kpis(stats: dict, branch_count: int) -> None:
    raw = stats.get("raw_transactions", 0) or 0
    pending = stats.get("pending", 0) or 0
    approved = stats.get("approved", 0) or 0
    turnover = stats.get("turnover", 0) or 0
    st.markdown(
        f"""
<div class="kpis">
  <div class="kpi">
    <div class="lab">Transaksi masuk</div>
    <div class="val">{num(raw)}</div>
    <div class="cap">semua status, sepanjang waktu</div>
  </div>
  <div class="kpi">
    <div class="lab">Menunggu review</div>
    <div class="val hue">{num(pending)}</div>
    <div class="cap">butuh keputusan</div>
  </div>
  <div class="kpi">
    <div class="lab">Disetujui</div>
    <div class="val">{num(approved)}</div>
    <div class="cap">siap dikirim ke Accurate</div>
  </div>
  <div class="kpi">
    <div class="lab">Turnover</div>
    <div class="val">{rp(turnover)}</div>
    <div class="cap">dari {raw} transaksi · {branch_count} cabang aktif</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


# ── review page ─────────────────────────────────────────────────────────────
STATUS = [("PENDING", "Menunggu"), ("APPROVED", "Disetujui"), ("REJECTED", "Ditolak"), ("SYNCED", "Tersinkron"), ("ALL", "Semua")]


def page_review(branch_code: str | None) -> None:
    codes = [c for c, _ in STATUS]
    radio_default("status_tab", codes, "PENDING")

    with st.container(key="status_tabs"):
        st.radio(
            "Status",
            codes,
            format_func=lambda c: dict(STATUS)[c],
            key="status_tab",
            horizontal=True,
            label_visibility="collapsed",
        )
    status = st.session_state.get("status_tab", "PENDING")

    rows = list_drafts(None if status == "ALL" else status, 500, branch_code=branch_code)

    # left rail 300px + detail
    col_rail, col_detail = st.columns([1, 2.55], gap="medium")

    with col_rail:
        with st.container(key="rail"):
            st.markdown(
                f'<div class="rail-head"><span class="t">Antrian</span>'
                f'<span class="c">{len(rows)} draft</span></div>',
                unsafe_allow_html=True,
            )
            if not rows:
                st.markdown(
                    '<div class="rail-empty">Belum ada draft di status ini.'
                    "<br>Coba tab lain, atau muat contoh di <b>Alat &amp; demo</b>.</div>",
                    unsafe_allow_html=True,
                )
                selected = None
            else:
                ids = [r["id"] for r in rows]
                if st.session_state.get("rail_radio") not in ids:
                    st.session_state["rail_radio"] = ids[0]
                st.radio(
                    "Draft",
                    ids,
                    format_func=lambda i: _rail_label(next(r for r in rows if r["id"] == i)),
                    key="rail_radio",
                    label_visibility="collapsed",
                    width="stretch",
                )
                selected = next(r for r in rows if r["id"] == st.session_state["rail_radio"])

    with col_detail:
        with st.container(key="detail"):
            if selected is None:
                st.markdown(
                    '<p style="color:var(--muted);font-size:13px;margin-top:8px;">'
                    "Pilih draft di antrian untuk melihat baris jurnal.</p>",
                    unsafe_allow_html=True,
                )
            else:
                render_detail(selected)


def _rail_label(r: dict) -> str:
    return (
        f"{r['draft_no']}  ·  {rp(r['total_debit'])}  ·  "
        f"{r.get('branch_code') or '—'}  ·  {r['business_date']}"
    )


def render_detail(draft: dict) -> None:
    status = draft["status"]
    branch = f"{draft.get('branch_code') or '—'} · {draft.get('branch_name') or '—'}"
    reviewer = draft.get("reviewed_by")
    reviewed_at = draft.get("reviewed_at")
    reviewed_txt = ""
    if reviewer:
        when = reviewed_at.strftime("%d %b %Y %H:%M") if hasattr(reviewed_at, "strftime") else reviewed_at
        reviewed_txt = f" &nbsp;·&nbsp; direview <b>{reviewer}</b> {when}"

    st.markdown(
        f"""
<div class="d-head">
  <div class="row1"><span class="no">{draft['draft_no']}</span>{pill(status)}</div>
  <div class="meta">
    Invoice <b>{draft['external_id']}</b> &nbsp;·&nbsp; {draft['business_date']}
    &nbsp;·&nbsp; {branch} &nbsp;·&nbsp; engine <b>{draft.get('ai_model') or '—'}</b>
    &nbsp;·&nbsp; confidence <b>{draft.get('confidence') if draft.get('confidence') is not None else '—'}</b>{reviewed_txt}
  </div>
  <div class="amt">{rp(draft['total_debit'])}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    items = draft.get("items") or []
    if items:
        sum_debit = sum(it.get("debit", 0) or 0 for it in items)
        sum_credit = sum(it.get("credit", 0) or 0 for it in items)
        diff = round(sum_debit - sum_credit, 2)
        balanced = diff == 0
        badge = (
            '<span class="pill pill-positive">Seimbang</span>'
            if balanced
            else '<span class="pill pill-negative">Selisih '
            + rp(abs(diff))
            + "</span>"
        )
        st.markdown(
            '<div class="totals">'
            '<div class="cell"><div class="lab">Total debit</div>'
            f'<div class="val">{rp(sum_debit)}</div></div>'
            '<div class="cell"><div class="lab">Total kredit</div>'
            f'<div class="val">{rp(sum_credit)}</div></div>'
            '<div class="cell"><div class="lab">Keseimbangan</div>'
            f'<div class="val state">{badge}'
            f'<span style="font-size:12px;color:var(--muted);font-weight:400;">{len(items)} baris</span>'
            "</div></div></div>",
            unsafe_allow_html=True,
        )

        body = "".join(
            "<tr>"
            f"<td class='n'>{it['line_no']}</td>"
            f"<td class='code'>{it['account_code']}</td>"
            f"<td>{it['account_name']}</td>"
            f"<td class='n'>{rp(it['debit']) if it.get('debit') else '—'}</td>"
            f"<td class='n'>{rp(it['credit']) if it.get('credit') else '—'}</td>"
            f"<td class='desc'>{it.get('description') or '—'}</td>"
            "</tr>"
            for it in items
        )

        cards = "".join(
            "<div class='it'>"
            f"<div><span class='code'>{it['account_code']}</span>"
            f" <span class='name'>{it['account_name']}</span></div>"
            f"<div class='dr'><span class='lab'>Debit</span>"
            f"<span class='val'>{rp(it['debit']) if it.get('debit') else '—'}</span></div>"
            f"<div class='cr'><span class='lab'>Kredit</span>"
            f"<span class='val'>{rp(it['credit']) if it.get('credit') else '—'}</span></div>"
            f"<div class='desc'>{it.get('description') or '—'}</div>"
            "</div>"
            for it in items
        )

        st.markdown(
            '<div class="jt-items only-mobile">' + cards + "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="jt-wrap only-desktop"><table class="jt">'
            "<thead><tr><th class='n'>#</th><th>Kode</th><th>Akun</th>"
            "<th class='n'>Debit</th><th class='n'>Kredit</th><th>Keterangan</th></tr></thead>"
            f"<tbody>{body}</tbody>"
            "<tfoot><tr><td colspan='3'>Total</td>"
            f"<td class='n'>{rp(sum_debit)}</td>"
            f"<td class='n'>{rp(sum_credit)}</td>"
            f"<td>{badge}</td></tr></tfoot>"
            "</table></div>",
            unsafe_allow_html=True,
        )
        if not balanced:
            st.warning("Total debit dan kredit tidak sama. Jangan approve sebelum dibetulkan.")
    else:
        st.caption("Tidak ada baris jurnal pada draft ini.")

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    if status == "PENDING":
        c1, c2, c3, _ = st.columns([1, 1, 1.4, 1.9])
        with c1:
            if st.button("Approve", key="act_ok", type="primary", width="stretch"):
                set_draft_status(draft["id"], "APPROVED", REVIEWER)
                st.rerun()
        with c2:
            if st.button("Reject", key="act_no", type="secondary", width="stretch"):
                set_draft_status(draft["id"], "REJECTED", REVIEWER)
                st.rerun()
        with c3:
            if st.button("Hitung ulang", key="act_re", type="secondary", width="stretch"):
                info = recompute_draft(draft["id"])
                st.toast(f"{info['items']} baris · {rp(info['total_debit'])}")
                st.rerun()
    else:
        c1, _ = st.columns([1.3, 2.7])
        with c1:
            if st.button("Kembalikan ke antrian", key="act_back", type="secondary", width="stretch"):
                set_draft_status(draft["id"], "PENDING", REVIEWER)
                st.rerun()

    with st.expander("Alasan mapping"):
        st.write(draft.get("ai_reasoning") or "Belum ada catatan.")
        if draft.get("payload"):
            st.json(draft["payload"], expanded=False)


# ── COA ─────────────────────────────────────────────────────────────────────
def page_coa() -> None:
    rows = list_coa_rows()
    if not rows:
        st.markdown(
            '<div class="panel"><h4>Buku besar kosong</h4>'
            '<div class="hint">Jalankan <code>python sql/create_db.py</code> untuk inisialisasi skema dan seed COA.</div></div>',
            unsafe_allow_html=True,
        )
        return

    body = "".join(
        "<tr>"
        f"<td class='code'>{r['account_code']}</td>"
        f"<td>{r['account_name']}</td>"
        f"<td style='color:var(--muted);'>{r['account_type']}</td>"
        f"<td class='n'>{r['normal_balance']}</td>"
        f"<td class='n'>{'Ya' if r['is_active'] else 'Tidak'}</td>"
        f"<td style='color:var(--muted);'>{(r.get('description') or '—')[:70]}</td>"
        "</tr>"
        for r in rows
    )
    st.markdown(
        f"<div style='font-size:12px;color:var(--muted);margin-bottom:10px;'>{len(rows)} akun</div>"
        "<table class='plain'>"
        "<thead><tr><th>Kode</th><th>Nama akun</th><th>Tipe</th>"
        "<th class='n'>Saldo normal</th><th class='n'>Aktif</th><th>Catatan</th></tr></thead>"
        f"<tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )

    with st.expander("Aturan mapping yang aktif"):
        st.code(
            "CASH          → D 1100 Kas\n"
            "QRIS          → D 1120 Settlement QRIS\n"
            "DEBIT / EDC   → D 1121 Settlement EDC\n"
            "MDR           → D 6100 Beban MDR\n"
            "DPP           → K 4100 Pendapatan penjualan\n"
            "Service       → K 4110 Pendapatan service charge\n"
            "PB1           → K 2100 Utang pajak PB1",
            language=None,
        )


# ── branches ────────────────────────────────────────────────────────────────
def page_branches() -> None:
    rows = list_branches()
    if not rows:
        st.markdown(
            '<div class="panel"><h4>Tabel cabang belum ada</h4>'
            '<div class="hint">Jalankan <code>sql/003_branches.sql</code> di lokal, '
            "atau <code>sql/supabase_setup.sql</code> di Supabase.</div></div>",
            unsafe_allow_html=True,
        )
        return

    usage = {b["id"]: branch_usage(b["id"]) for b in rows}
    body = "".join(
        "<tr>"
        f"<td class='code'>{b['branch_code']}</td>"
        f"<td>{b['branch_name']}</td>"
        f"<td style='color:var(--muted);'>{b['city'] or '—'}</td>"
        f"<td>{pill('SYNCED') if b['is_active'] else '<span class=\"pill pill-negative\">Nonaktif</span>'}</td>"
        f"<td class='n'>{num(usage[b['id']]['raw_transactions'])}</td>"
        f"<td class='n'>{num(usage[b['id']]['drafts'])}</td>"
        "</tr>"
        for b in rows
    )
    st.markdown(
        f"<div style='font-size:12px;color:var(--muted);margin-bottom:10px;'>{len(rows)} cabang</div>"
        "<table class='plain'>"
        "<thead><tr><th>Kode</th><th>Nama</th><th>Kota</th><th>Status</th>"
        "<th class='n'>Transaksi</th><th class='n'>Draft</th></tr></thead>"
        f"<tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption("Kode dipakai di payload JSON dan filter. Nama serta kota yang muncul di dashboard dan file Excel.")

    st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)

    left, right = st.columns(2, gap="medium")

    with left:
        with st.form("add_branch", border=True):
            st.markdown("##### Tambah cabang")
            code = st.text_input("Kode", placeholder="GALAXY")
            name = st.text_input("Nama", placeholder="Galaxy")
            city = st.text_input("Kota", placeholder="Bekasi")
            if st.form_submit_button("Tambah", type="primary", width="stretch"):
                try:
                    made = create_branch(code, name, city)
                    st.toast(f"Cabang {made['branch_code']} ditambahkan.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(friendly(exc))

    with right:
        labels = {f"{b['branch_code']} · {b['branch_name']}": b for b in rows}
        with st.form("edit_branch", border=True):
            st.markdown("##### Ubah cabang")
            picked = st.selectbox("Cabang", list(labels))
            target = labels[picked]
            u = usage[target["id"]]
            code = st.text_input("Kode", value=target["branch_code"])
            name = st.text_input("Nama", value=target["branch_name"])
            city = st.text_input("Kota", value=target["city"] or "")
            active = st.checkbox("Aktif", value=bool(target["is_active"]))
            if st.form_submit_button("Simpan", type="primary", width="stretch"):
                try:
                    upd = update_branch(
                        target["id"],
                        branch_code=code,
                        branch_name=name,
                        city=city,
                        is_active=active,
                    )
                    st.toast(f"Tersimpan: {upd['branch_code']} · {upd['branch_name']}")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(friendly(exc))
        st.caption(
            f"{num(u['raw_transactions'])} transaksi dan {num(u['drafts'])} draft menempel di cabang ini. "
            "Mengubah kode atau nama tidak memindahkan data."
        )

    with st.expander("Hapus cabang"):
        st.caption("Hanya cabang tanpa transaksi dan tanpa draft yang bisa dihapus. Kalau sudah ada data, nonaktifkan saja.")
        target = labels[st.selectbox("Cabang yang dihapus", list(labels), key="del_pick")]
        sure = st.checkbox("Saya yakin", key=f"del_ok_{target['id']}")
        if st.button("Hapus permanen", key=f"del_go_{target['id']}", disabled=not sure, type="secondary"):
            try:
                delete_branch(target["id"])
                st.toast(f"Cabang {target['branch_code']} dihapus.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(friendly(exc))


# ── utils ───────────────────────────────────────────────────────────────────
def page_utils() -> None:
    samples = load_samples()

    with st.container(border=True):
        st.markdown("##### Contoh transaksi")
        if not samples:
            st.caption("Folder `data/samples/` kosong.")
        for name, payload in samples.items():
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            with c1:
                st.markdown(f"<div style='font-size:13px;'>{name}</div>", unsafe_allow_html=True)
            with c2:
                if st.button("Muat", key=f"s_{name}", width="stretch"):
                    try:
                        raw_id, draft_id = ingest_transaction(payload)
                        st.toast(f"Masuk: raw {raw_id}, draft {draft_id}")
                        st.rerun()
                    except (ValueError, MappingError) as exc:
                        st.error(str(exc))

    with st.container(border=True):
        st.markdown("##### Upload JSON")
        st.caption("Payload transaksi Accurate POS. Cabang diambil dari pilihan di bawah.")
        up = st.file_uploader("File JSON", type=["json"], label_visibility="collapsed")
        opts = [b["branch_code"] for b in list_branches(active_only=True)]
        target = st.selectbox("Cabang tujuan", opts, key="up_branch") if opts else None
        if not opts:
            st.caption("Belum ada cabang aktif. Tambahkan dulu di menu Cabang.")
        if up and st.button("Proses upload", type="primary", disabled=not target):
            try:
                payload = json.loads(up.read().decode("utf-8"))
                payload["branch_code"] = target
                raw_id, draft_id = ingest_transaction(payload)
                st.toast(f"Masuk: raw {raw_id}, draft {draft_id}")
                st.rerun()
            except (ValueError, MappingError, json.JSONDecodeError) as exc:
                st.error(str(exc))

    with st.container(border=True):
        st.markdown("##### Kalkulator")
        st.caption("Hitung cepat tanpa menyimpan apa pun.")
        with st.form("calc"):
            c1, c2, c3 = st.columns(3)
            qty = c1.number_input("Qty", 1, 999, 1)
            price = c2.number_input("Harga satuan", 0, 100_000_000, 50_000, step=1_000)
            disc = c3.number_input("Diskon bill", 0, 100_000_000, 0, step=1_000)
            c4, c5 = st.columns(2)
            pb1 = c4.number_input("PB1 (%)", 0.0, 30.0, 10.0, step=0.5)
            svc = c5.number_input("Service (%)", 0.0, 30.0, 0.0, step=0.5)
            go = st.form_submit_button("Hitung", type="primary")
        if go:
            payload = {
                "invoice_no": f"SIM-{uuid.uuid4().hex[:6].upper()}",
                "business_date": "2026-11-02",
                "tax": {"pb1_rate": pb1 / 100, "service_charge_rate": svc / 100, "tax_inclusive": False},
                "lines": [{"item_name": "Simulasi", "qty": int(qty), "unit_price": price}],
                "bill_discount": disc,
                "payments": [{"method": "CASH", "gross_amount": 10**12, "mdr_rate": 0.0}],
            }
            res = calculate(payload)
            rows = [
                ("DPP", rp(res.dpp)),
                ("Service charge", rp(res.service_charge)),
                ("PB1", rp(res.tax)),
                ("Total", rp(res.total_due)),
                ("Kembalian", rp(res.change_due)),
            ]
            st.markdown(
                "<table class='plain' style='margin-top:8px;'>"
                + "".join(f"<tr><td>{k}</td><td class='n'>{v}</td></tr>" for k, v in rows)
                + "</table>",
                unsafe_allow_html=True,
            )

    with st.container(border=True):
        st.markdown("##### Ekspor ke Google Drive")
        st.caption("Excel mingguan berisi draft APPROVED tujuh hari terakhir.")
        try:
            from app.drive_export import export_to_drive, gdrive_available

            drive_ok = gdrive_available()
        except Exception:  # noqa: BLE001
            drive_ok = False
        if drive_ok:
            if st.button("Push sekarang", type="primary"):
                try:
                    out = export_to_drive(since_days=7, only_approved=True)
                    if out.get("status") == "uploaded":
                        st.success(f"{out['draft_count']} draft terkirim.")
                        st.link_button("Buka file", out["web_view_link"])
                    else:
                        st.info(out.get("message", "Tidak ada data untuk dikirim."))
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Gagal: {exc}")
        else:
            st.caption(
                "Tombol ini hanya muncul di mesin lokal (butuh token OAuth Google). "
                "Ekspor otomatis tetap jalan tiap Minggu 09:00 WIB lewat cron lokal."
            )

    with st.expander("Zona berbahaya"):
        st.caption("Menghapus semua transaksi dan draft. COA dan cabang tetap.")
        if st.checkbox("Saya yakin", key="reset_ok") and st.button("Hapus semua data", type="secondary"):
            reset_all()
            st.toast("Semua data transaksi dihapus.")
            st.rerun()


# ── main ────────────────────────────────────────────────────────────────────
def main() -> None:
    inject_css()

    # Centralized password gate; returns the reviewer name entered at login.
    global REVIEWER
    REVIEWER = require_login()

    ok, err = db_check()
    if not ok:
        with st.container(key="login"):
            st.markdown('<div class="login-h">Database tidak terjangkau</div>', unsafe_allow_html=True)
            st.markdown('<p class="login-p">Cek <code>DATABASE_URL</code> di <code>.env</code> lokal atau Streamlit Cloud → Secrets.</p>', unsafe_allow_html=True)
            st.code(err)
            if st.button("Keluar"):
                logout()
                st.rerun()
        st.stop()

    # Render both navigation surfaces: sidebar for desktop, compact pills for phones.
    page = render_sidebar(REVIEWER)
    render_mobile_nav(REVIEWER)
    branches = [b for b in list_branches() if b["is_active"]]
    branch_code = render_topbar(page, branches, st.session_state.get("branch_code"))

    with st.container(key="content"):
        render_kpis(get_stats(branch_code), len(branches))
        if page == "review":
            page_review(branch_code)
        elif page == "coa":
            page_coa()
        elif page == "branches":
            page_branches()
        else:
            page_utils()


main()