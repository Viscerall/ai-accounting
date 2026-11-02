# Deploy Publik — Jalur A (Streamlit Community Cloud + Supabase)

Tujuan: dashboard bisa diakses publik lewat URL gratis, **dikunci password**, dan datanya
disimpan di Postgres gratis selamanya (500 MB).

```
Browser publik  ──►  Streamlit Community Cloud (gratis, auto-deploy dari GitHub)
                          │
                          └──►  Supabase Postgres (500 MB gratis)  ◄──  cron lokal Minggu 09:00 ──► GDrive Excel
```

Biaya: **Rp 0**. Yang perlu dibuat: akun Supabase, akun GitHub (sudah ada), akun Streamlit.

---

## 📱 Bisa semua dari HP?

Ya, hampir semua — asal **jangan** pakai `python sql/create_db.py`.
Ganti dengan paste SQL di browser.

| Langkah | Dari HP? | Caranya |
|---|---|---|
| Bikin project Supabase | ✅ | Browser → supabase.com |
| Bikin tabel + COA | ✅ | Supabase → **SQL Editor** → paste `sql/supabase_setup.sql` → Run |
| Bikin repo GitHub | ✅ | Sudah jadi: `Viscerall/ai-accounting` |
| Deploy Streamlit Cloud | ✅ | share.streamlit.io → GitHub → isi Secrets |
| Update kode kecil (typo) | ✅ | Edit langsung di github.com |
| Update kode besar | ❌ | Butuh laptop / terminal |
| Cron GDrive Minggu 09:00 | ❌ | Butuh laptop nyala + token OAuth |

### Langkah SQL dari HP (pengganti `create_db.py`)

1. Supabase → project kamu → **SQL Editor** → **New query**
2. Buka <https://github.com/Viscerall/ai-accounting/blob/main/sql/supabase_setup.sql>
   di tab lain → klik **Copy raw file**
3. Paste ke SQL Editor → **Run**
4. Cek **Table Editor**: 7 tabel + 16 akun COA

File itu **idempotent** — aman di-run dua kali, tidak error.

---

## 0. Yang sudah disiapkan di repo

| File | Fungsi |
|---|---|
| `app/auth.py` | Gerbang password (`APP_PASSWORD`), fail-closed kalau belum di-set |
| `.streamlit/config.toml` | Tema + `headless` untuk server |
| `.streamlit/secrets.toml.example` | Template secrets untuk Streamlit Cloud |
| `.gitignore` | `.env` & `.streamlit/secrets.toml` **tidak** ikut ter-commit |
| `requirements.txt` | Termasuk `openpyxl` untuk ekspor Excel |

---

## 1. Bikin database di Supabase

1. Buka <https://supabase.com> → **Start your project** (login pakai GitHub).
2. **New project**:
   - Name: `ai-accounting`
   - Database Password: **catat/simpan** (ini password Postgres, bukan password dashboard)
   - Region: **Southeast Asia (Singapore)** — paling dekat ke Indonesia
   - Plan: **Free**
3. Tunggu ±2 menit sampai project siap.
4. Ambil connection string lewat tombol **Connect** di **bar atas halaman project**
   (bukan di Project Settings — sejak UI baru, menu di sana tidak punya opsi "Database").
   Link langsung: <https://supabase.com/dashboard/project/_?showConnect=true&method=session>

   Di panel Connect: pilih **Direct** → tab **Session pooler** → format **URI**.
   Bentuknya:

   ```
   postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
   ```

   **Wajib Session pooler, bukan Direct connection.** Direct connection sekarang
   IPv6-only; Streamlit Community Cloud jalan di IPv4, jadi app akan gagal connect.

   Huruf `$` di password aman apa adanya di dalam string. Tapi karakter ini **harus**
   di-encode: `@`→`%40`, `#`→`%23`, `?`→`%3F`, `/`→`%2F`, `:`→`%3A`, `&`→`%26`,
   `%`→`%25`, spasi→`%20`. Paling gampang: bikin database password dari huruf+angka saja.
   Tambahkan `?sslmode=require` di belakang string.

> **Storage**: free tier Supabase = 500 MB database. Data jurnal teks (nominal + kode akun)
> sangat kecil — 1 transaksi ± 1–2 KB. Artinya ± 250.000–500.000 transaksi.
> File Excel/foto **tidak** disimpan di Supabase, tapi di Google Drive.

## 2. Isi schema + COA ke Supabase

Di mesin lokal, pakai connection string Supabase (bukan localhost):

```bash
cd C:/Users/nizar/ai-accounting
export DATABASE_URL="postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require"
python sql/create_db.py
```

Script ini bikin 7 tabel + seed 16 akun COA. Cek di Supabase → **Table Editor**,
harusnya sudah kelihatan tabel `raw_transactions`, `journal_drafts`, `journal_draft_items`, `chart_of_accounts`, dan tabel audit/operasional lainnya.

## 3. Bikin repo GitHub

Repo sudah di-push otomatis ke:

```
https://github.com/Viscerall/ai-accounting
```

Kalau mau bikin sendiri dari nol:

```bash
gh repo create ai-accounting --public --source=. --remote=origin --push
```

> **Public vs Private**: Streamlit Community Cloud bisa deploy dari repo **private** juga
> (gratis, login GitHub yang sama). Kalau tidak nyaman kode terbuka, set repo private —
> app tetap bisa diakses publik.

## 4. Deploy di Streamlit Community Cloud

1. Buka <https://share.streamlit.io> → login pakai GitHub → **Create app**.
2. Isi:
   - **Repository**: `Viscerall/ai-accounting`
   - **Branch**: `main`
   - **Main file path**: `dashboard.py`
   - **App URL**: pilih subdomain, misal `ai-accounting-nizar` → jadi
     `https://ai-accounting-nizar.streamlit.app`
3. **Sebelum klik Deploy**, buka **Advanced settings → Secrets** dan paste:

   ```toml
   APP_PASSWORD = "[SET_YOUR_PRIVATE_PASSWORD]"
   DATABASE_URL = "postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require"
   HERMES_ENGINE = "rules"
   HERMES_PROMPT_TIMEOUT = "30"
   ```

4. **Deploy**. Build pertama ±3–5 menit (install requirements).
5. Buka URL app → harusnya muncul layar **login password**, bukan dashboard.

## 5. Ganti password nanti

Streamlit Cloud → app kamu → **⋮ → Settings → Secrets** → ubah `APP_PASSWORD` → **Save**.
App restart otomatis. Tidak perlu commit apa pun.

---

## Cara kerja password

- Password disimpan di **Streamlit Secrets**, bukan di kode, bukan di repo.
- Perbandingan pakai `hmac.compare_digest` (constant-time, tidak bisa ditebak lewat timing).
- Login disimpan di `st.session_state` — hilang saat tab ditutup / app restart.
- Kalau `APP_PASSWORD` kosong → dashboard **menolak jalan** (fail-closed), bukan terbuka.
- Tombol **Logout** ada di sidebar bawah.

## Yang tetap jalan lokal

| Fitur | Di Cloud | Di Lokal |
|---|---|---|
| Review / approve / reject jurnal | ✅ | ✅ |
| Lihat KPI & COA | ✅ | ✅ |
| Ekspor Excel manual ke GDrive | ❌ (butuh `google_api.py` + token OAuth lokal) | ✅ |
| Ekspor otomatis Minggu 09:00 → GDrive | ❌ | ✅ (Hermes cron `70bb99f016b4`) |

**Penting:** cron GDrive tetap di laptop karena butuh token OAuth Google.
Supaya tetap jalan, laptop harus nyala hari Minggu. Kalau mati, jalankan manual:

```bash
python scripts/weekly_export.py --force
```

## 🛠 Akses DB lewat DBeaver

DBeaver (Community, gratis) sudah terinstall di laptop: `C:/Users/nizar/AppData/Local/DBeaver`.
Ada **dua** database yang bisa dibuka — jangan ketuker:

### A. Lokal (Postgres 18 di laptop)

| Field | Nilai |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `ai_accounting` |
| User | `postgres` |
| Password | password Postgres lokal (bukan password Supabase) |
| SSL | **OFF** |

Isi tabel: `chart_of_accounts`, `raw_transactions`, `journal_drafts`,
`journal_draft_items`, `raw_bank_statements`, `daily_cash_counts`, `audit_log`.

### B. Supabase (cloud — ini yang dipakai web app)

New Database Connection → **PostgreSQL**, lalu:

| Field | Nilai |
|---|---|
| Host | `aws-0-ap-southeast-1.pooler.supabase.com` |
| Port | `5432` (**Session pooler**) |
| Database | `postgres` |
| User | `postgres.<PROJECT_REF>` |
| Password | password DB Supabase (waktu bikin project) |
| SSL | **ON** → `sslmode = require` |

`PROJECT_REF` ada di Supabase → **Settings → General → Reference ID**
(bisa juga dibaca dari connection string di tombol **Connect**).

Ambil string lengkapnya: Supabase → tombol **Connect** (bar atas project) →
**Session pooler** → tab **URI**:

```
postgresql://postgres.PROJECT_REF:***@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require
```

**Dua jebakan yang sering bikin gagal connect:**

- **Transaction pooler (port 6543)** tidak cocok untuk DBeaver — dia tidak mendukung
  prepared statement / fitur session yang dipakai client tools. Pakai **5432**.
- **Direct connection** (`db.<ref>.supabase.co:5432`) sekarang **IPv6-only** → sering
  timeout dari jaringan biasa. Selalu pakai host `*.pooler.supabase.com`.

Password DB Supabase **tidak disimpan di repo** (cuma ada di Streamlit Secrets).
Kalau lupa: Supabase → Settings → Database → **Reset database password**, lalu update
juga `DATABASE_URL` di Streamlit Secrets (dan `.env` lokal kalau dipakai).

## Batasan free tier (biar tidak kaget)

| Limit | Nilai | Dampak |
|---|---|---|
| Supabase DB | 500 MB | Cukup ratusan ribu transaksi |
| Supabase idle | Project di-pause setelah 7 hari tidak ada aktivitas | Buka dashboard = aktivitas, jadi aman |
| Streamlit Cloud | App "sleep" setelah tidak diakses lama | Request pertama agak lambat (±30 detik), lalu normal |
| Streamlit Cloud RAM | 1 GB | Cukup untuk app ini |

## Troubleshooting

**"Tidak bisa connect ke database"**
→ Secrets `DATABASE_URL` salah / lupa `?sslmode=require`. Cek di Supabase → Settings → Database.

**Layar login muncul terus walau password benar**
→ `APP_PASSWORD` di Secrets ada spasi/quote nyangkut. Isi dengan password privatmu sendiri, tanpa menaruhnya di repo.

**App error `ModuleNotFoundError`**
→ Ada dependency baru yang belum masuk `requirements.txt`. Tambah, commit, push — Streamlit auto-rebuild.

**Tabel kosong di cloud padahal lokal ada data**
→ Lokal pakai Postgres localhost, cloud pakai Supabase. Dua database terpisah.
Untuk pindah data: `pg_dump` lokal lalu restore ke Supabase, atau input ulang via dashboard.

**`Invalid format: please enter valid TOML` di Streamlit Secrets**
→ Ada Enter/baris baru di tengah `DATABASE_URL`. TOML tidak mengizinkan string
terpotong baris. Pastikan satu variabel = satu baris fisik, dan pakai petik satu `'`
supaya `$` aman:
```
DATABASE_URL = 'postgresql://...?sslmode=require'
```
Tampilan boleh ter-*wrap* ke bawah di layar HP — yang dilarang itu karakter Enter asli.

**SQL Editor minta konfirmasi "Run and enable RLS"**
→ Pilih **Run and enable RLS** (tombol hijau). Tanpa RLS, tabel di schema `public`
bisa dibaca/ditulis siapa pun lewat REST API Supabase memakai `anon` key yang publik.
App kita tidak terpengaruh: dia konek sebagai role `postgres` (pemilik tabel),
dan pemilik tabel otomatis bypass RLS.

