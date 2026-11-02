-- --------------------------------------------------
-- AI ACCOUNTING MIGRATION 003 — multi-cabang (cafe branches)
--
-- Jalankan SEKALI di database yang sudah ada (local Postgres / Supabase):
--   psql -U postgres -d ai_accounting -f sql/003_branches.sql
--   Supabase: SQL Editor -> paste file ini -> Run
--
-- Idempotent: aman dijalankan berulang kali.
-- --------------------------------------------------

-- 1. Tabel cabang
create table if not exists branches (
  id bigserial primary key,
  branch_code text unique not null check (char_length(branch_code) <= 20),
  branch_name text not null check (char_length(branch_name) <= 100),
  city text,
  address text,
  phone text,
  opened_at date,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);
alter table branches enable row level security;

-- 2. Seed cabang default
--    Ganti nama/kota sesuai cabang asli, atau tambah baris baru.
insert into branches (branch_code, branch_name, city, opened_at, is_active) values
  ('PUSAT', 'Cabang Utama', 'Bogor',   '2026-11-01', true),
  ('CAB2',  'Cabang 2',     'Jakarta', '2026-11-01', true)
on conflict (branch_code) do nothing;

-- 3. Tambah branch_id ke tabel transaksi + default PUSAT + backfill data lama
do $$
declare
  pusat_id bigint;
  tbl text;
begin
  select id into pusat_id from branches where branch_code = 'PUSAT';
  foreach tbl in array array['raw_transactions','journal_drafts','raw_bank_statements','daily_cash_counts']
  loop
    execute format('alter table %I add column if not exists branch_id bigint references branches(id) on delete restrict', tbl);
    execute format('alter table %I alter column branch_id set default %s', tbl, pusat_id);
    execute format('update %I set branch_id = %s where branch_id is null', tbl, pusat_id);
  end loop;
end $$;

-- 4. Index per cabang (buat filter & laporan per cabang cepat)
create index if not exists idx_raw_transactions_branch_id   on raw_transactions(branch_id);
create index if not exists idx_journal_drafts_branch_id     on journal_drafts(branch_id);
create index if not exists idx_daily_cash_counts_branch_id  on daily_cash_counts(branch_id);
create index if not exists idx_raw_bank_statements_branch_id on raw_bank_statements(branch_id);

-- 5. Invoice unik PER CABANG (bukan global)
alter table raw_transactions drop constraint if exists raw_transactions_external_id_key;
create unique index if not exists uq_raw_transactions_branch_external_id
  on raw_transactions (branch_id, external_id);

-- 6. Cash count unik per cabang + tanggal + shift + kasir
alter table daily_cash_counts drop constraint if exists daily_cash_counts_close_date_shift_type_cashier_key;
create unique index if not exists uq_daily_cash_counts_branch_shift
  on daily_cash_counts (branch_id, close_date, shift_type, cashier);

-- 7. Verify
select b.branch_code, b.branch_name, b.city, b.is_active,
       (select count(*) from raw_transactions    r where r.branch_id = b.id) as trx,
       (select count(*) from journal_drafts      j where j.branch_id = b.id) as draft
from branches b
order by b.branch_code;