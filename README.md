# Dawend — Jurnal Otomatis untuk Kafe

MVP Scenario A: **Python lokal + Postgres + Streamlit**.

Prinsip inti: **angka dihitung rules engine deterministik (Decimal), bukan LLM.**

## Struktur

```
ai-accounting/
├─ app/
│  ├─ calculator.py       # math: subtotal, diskon, PB1, service, MDR, settlement, kembalian
│  ├─ mapping_rules.py    # payload → baris jurnal (debit=kredit dijaga)
│  ├─ db.py               # akses Postgres (psycopg3)
│  ├─ config.py           # baca .env
│  └─ cli.py              # CLI: ingest / list / coa / reset / approve
├─ sql/
│  ├─ 001_schema.sql      # 6 tabel
│  ├─ 002_seed_coa.sql    # 16 akun COA dummy
│  └─ create_db.py        # bikin DB + apply schema + seed
├─ data/samples/*.json    # 3 contoh transaksi
├─ tests/                 # 15 unit test
├─ dashboard.py           # Streamlit UI
└─ .env                   # DATABASE_URL, HERMES_ENGINE=rules
```

## Jalanin

```bash
# 1. sekali saja: bikin DB + schema + COA
python sql/create_db.py

# 2. buka dashboard
python -m streamlit run dashboard.py      # http://localhost:8501

# opsional: isi data contoh lewat CLI
python -m app.cli ingest data/samples/qris_sale.json
python -m app.cli list
```

## Isi dashboard

- **KPI row** — raw transaksi, pending, approved, rejected, synced, turnover (approved).
- **Tab Review Draft** — filter status, tabel draft, pilih satu → detail baris jurnal, alasan mapping, tombol Approve / Reject / Recompute, balikin ke PENDING.
- **Tab COA** — 16 akun + tabel mapping rules aktif.
- **Tab Demo & Utils** — ingest 3 sample, upload JSON, kalkulator manual (tanpa simpan), hapus semua data.
- **Sidebar** — tombol push ke Accurate Online sengaja disabled (API belum ada).

## Mapping rules

| Sumber | Akun |
|---|---|
| CASH | D 1100 Kas |
| QRIS | D 1120 Piutang Settlement QRIS |
| DEBIT/EDC | D 1121 Piutang Settlement EDC |
| MDR | D 6100 Beban MDR |
| DPP | K 4100 Pendapatan Penjualan |
| Service charge | K 4110 Pendapatan Service Charge |
| PB1 | K 2100 Utang Pajak PB1 |

## Test

```bash
python -m pytest tests/ -q      # 15 passed
```

## Status

- ✅ Hitung deterministik (Decimal, ROUND_HALF_UP) — 15 test
- ✅ Mapping jurnal balance — 3 sample terverifikasi
- ✅ Dashboard render tanpa exception (Streamlit AppTest)
- ✅ Approve/Reject/Recompute lifecycle jalan
- ⛔ Sync ke Accurate Online — nunggu API
- ⛔ COA masih dummy, belum COA Accurate asli
