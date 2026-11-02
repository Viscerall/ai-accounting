-- ============================================================
--  AI ACCOUNTING — SETUP UNTUK SUPABASE (paste-ready)
--  Cara pakai: Supabase Dashboard -> SQL Editor -> New query
--  -> paste SELURUH file ini -> Run.
--  Aman dijalankan berulang kali (idempotent): tidak error kalau
--  tabel sudah ada / COA sudah ter-seed.
-- ============================================================

-- Helper: uuid-based ID untuk entity tambahan
create extension if not exists "uuid-ossp";

-- ------------------------------------------------------------
-- 1. CHART OF ACCOUNTS (Master COA)
-- ------------------------------------------------------------
create table if not exists chart_of_accounts (
  id bigserial primary key,
  account_code text unique not null check (char_length(account_code) <= 20),
  account_name text not null check (char_length(account_name) <= 200),
  account_type text not null check (account_type in ('ASSET','LIABILITY','EQUITY','REVENUE','COGS','EXPENSE')),
  normal_balance text not null check (normal_balance in ('DEBIT','CREDIT')),
  is_active boolean not null default true,
  description text,
  created_at timestamptz not null default now()
);

-- ------------------------------------------------------------
-- 2. RAW TRANSACTIONS (Staging)
-- ------------------------------------------------------------
create table if not exists raw_transactions (
  id bigserial primary key,
  source text not null default 'accurate_pos',
  external_id text unique not null,   -- invoice number / POS reference
  business_date date not null,
  payload jsonb not null,             -- original transaction payload
  status text not null default 'RECEIVED' check (status in ('RECEIVED','CALCULATED','DRAFTED','APPROVED','SYNCED','REJECTED','ERROR')),
  ingested_at timestamptz not null default now(),
  error_message text
);

-- ------------------------------------------------------------
-- 3. JOURNAL DRAFTS
-- ------------------------------------------------------------
create table if not exists journal_drafts (
  id bigserial primary key,
  raw_transaction_id bigint not null references raw_transactions(id) on delete cascade,
  draft_no text unique not null,
  journal_date date not null default (current_date),
  memo text,
  status text not null default 'PENDING' check (status in ('PENDING','APPROVED','REJECTED','SYNCED')),
  total_debit numeric(18,2) not null default 0,
  total_credit numeric(18,2) not null default 0,
  ai_model text,
  ai_reasoning text,
  confidence numeric(4,3),
  created_at timestamptz not null default now(),
  reviewed_at timestamptz,
  reviewed_by text
);

-- ------------------------------------------------------------
-- 4. JOURNAL DRAFT ITEMS (Baris rincian)
-- ------------------------------------------------------------
create table if not exists journal_draft_items (
  id bigserial primary key,
  journal_draft_id bigint not null references journal_drafts(id) on delete cascade,
  line_no int not null,
  account_id bigint not null references chart_of_accounts(id),
  debit numeric(18,2) not null default 0,
  credit numeric(18,2) not null default 0,
  description text,
  created_at timestamptz not null default now(),
  unique (journal_draft_id, line_no)
);

-- ------------------------------------------------------------
-- 5. DATA TABLES OPSIONAL (bank statements & cash counts)
-- ------------------------------------------------------------
create table if not exists raw_bank_statements (
  id bigserial primary key,
  bank_account text not null,
  statement_date date not null,
  amount numeric(18,2) not null,
  description text,
  transaction_id text,
  data jsonb,
  created_at timestamptz not null default now()
);

create table if not exists daily_cash_counts (
  id bigserial primary key,
  close_date date not null,
  shift_type text not null,           -- 'MORNING','DAY','NIGHT'
  cashier text not null,
  cash_in_drawer numeric(18,2) not null default 0,
  expected_amount numeric(18,2) not null default 0,
  difference numeric(18,2),
  remarks text,
  created_at timestamptz not null default now(),
  unique (close_date, shift_type, cashier)
);

-- ------------------------------------------------------------
-- 6. AUDIT LOG
-- ------------------------------------------------------------
create table if not exists audit_log (
  id bigserial primary key,
  table_name text not null,
  record_id bigint,
  action text not null check (action in ('INSERT','UPDATE','DELETE')),
  old_values jsonb,
  new_values jsonb,
  actor text not null default 'system',
  created_at timestamptz not null default now()
);

-- ------------------------------------------------------------
-- Indexes
-- ------------------------------------------------------------
create index if not exists idx_raw_transactions_status on raw_transactions(status);
create index if not exists idx_raw_transactions_business_date on raw_transactions(business_date);
create index if not exists idx_journal_drafts_status on journal_drafts(status);
create index if not exists idx_journal_draft_items_draft_id on journal_draft_items(journal_draft_id);
create index if not exists idx_audit_log_created_at on audit_log(created_at);

-- ------------------------------------------------------------
-- SEED: Chart of Accounts (kafe / restoran)
-- Aman diulang: kalau account_code sudah ada, dilewati.
-- ------------------------------------------------------------
insert into chart_of_accounts (account_code, account_name, account_type, normal_balance, description) values
  ('1100', 'Kas',                                  'ASSET',     'DEBIT',   'Uang tunai di laci kasir / safe'),
  ('1110', 'Kas di Bank (BCA)',                    'ASSET',     'DEBIT',   'Rekening utama kafe (BCA)'),
  ('1120', 'Piutang Settlement QRIS',              'ASSET',     'DEBIT',   'Uang bersih QRIS belum masuk bank (net, after MDR)'),
  ('1121', 'Piutang Settlement EDC',               'ASSET',     'DEBIT',   'Uang bersih EDC belum masuk bank (net, after MDR)'),
  ('1200', 'Persediaan Bahan Baku',                'ASSET',     'DEBIT',   'Stok bahan baku & HPP'),
  ('2100', 'Utang Pajak PB1',                      'LIABILITY', 'CREDIT',  'Pajak Barang/Jasa (Restoran) yang belum dibayar'),
  ('2110', 'Utang Service Charge',                 'LIABILITY', 'CREDIT',  'Service charge yang belum dibayarkan'),
  ('3100', 'Modal Pemilik',                        'EQUITY',    'CREDIT',  'Modal pemilik kafe'),
  ('4100', 'Pendapatan Penjualan',                 'REVENUE',   'CREDIT',  'Pendapatan penjualan makanan & minuman'),
  ('4110', 'Pendapatan Service Charge',            'REVENUE',   'CREDIT',  'Pendapatan dari service charge'),
  ('5100', 'Harga Pokok Penjualan',                 'COGS',      'DEBIT',   'HPP / bahan baku terpakai'),
  ('6100', 'Beban MDR / Payment Gateway',          'EXPENSE',   'DEBIT',   'Biaya fee QRIS (0,7%) / MDR EDC'),
  ('6110', 'Beban Gaji & Tunjangan',               'EXPENSE',   'DEBIT',   'Gaji karyawan, tips, bonus'),
  ('6120', 'Beban Sewa',                           'EXPENSE',   'DEBIT',   'Sewa tempat / peralatan'),
  ('6130', 'Beban Utilitas',                       'EXPENSE',   'DEBIT',   'Listrik, air, gas, internet'),
  ('6140', 'Beban Operasional Lainnya',             'EXPENSE',   'DEBIT',   'Biaya promosi, maintenance, dll.')
on conflict (account_code) do nothing;

-- ------------------------------------------------------------
-- VERIFIKASI: harus menampilkan 6 tabel dan 16 akun COA
-- ------------------------------------------------------------
select 'tabel' as jenis, count(*)::text as jumlah
from information_schema.tables
where table_schema = 'public'
  and table_name in ('chart_of_accounts','raw_transactions','journal_drafts',
                     'journal_draft_items','raw_bank_statements','daily_cash_counts','audit_log')
union all
select 'coa', count(*)::text from chart_of_accounts;
