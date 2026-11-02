-- --------------------------------------------------
-- AI ACCOUNTING MIGRATION 004 — replace branches
-- Ganti cabang lama (PUSAT, CAB2) dengan Mekarsari & Galaxy
--
-- Jalankan:
--   psql -U postgres -d ai_accounting -f sql/004_replace_branches.sql
--   Supabase: SQL Editor -> paste file ini -> Run
--
-- Idempotent: aman dijalankan berulang kali.
-- --------------------------------------------------

begin;

do $$
declare
  mek_id bigint;
  gal_id bigint;
  pusat_id bigint;
  cab2_id bigint;
  tbl text;
begin
  -- 1. Buat / perbarui cabang baru (idempotent)
  insert into branches (branch_code, branch_name, city, is_active)
  values ('MEKARSARI', 'Mekarsari', 'Bekasi', true)
  on conflict (branch_code) do update set
    branch_name = excluded.branch_name,
    city        = excluded.city,
    is_active   = true;

  insert into branches (branch_code, branch_name, city, is_active)
  values ('GALAXY', 'Galaxy', 'Bekasi', true)
  on conflict (branch_code) do update set
    branch_name = excluded.branch_name,
    city        = excluded.city,
    is_active   = true;

  select id into mek_id from branches where branch_code = 'MEKARSARI';
  select id into gal_id from branches where branch_code = 'GALAXY';

  -- 2. Pindahkan data PUSAT -> MEKARSARI
  select id into pusat_id from branches where branch_code = 'PUSAT';
  if pusat_id is not null then
    foreach tbl in array array['raw_transactions','journal_drafts','raw_bank_statements','daily_cash_counts'] loop
      if to_regclass('public.' || tbl) is not null then
        execute format('update %I set branch_id = %L where branch_id = %L', tbl, mek_id, pusat_id);
      end if;
    end loop;
  end if;

  -- 3. Pindahkan data CAB2 -> GALAXY
  select id into cab2_id from branches where branch_code = 'CAB2';
  if cab2_id is not null then
    foreach tbl in array array['raw_transactions','journal_drafts','raw_bank_statements','daily_cash_counts'] loop
      if to_regclass('public.' || tbl) is not null then
        execute format('update %I set branch_id = %L where branch_id = %L', tbl, gal_id, cab2_id);
      end if;
    end loop;
  end if;

  -- 4. Hapus cabang lama (hanya kalau sudah tidak dipakai)
  delete from branches where branch_code in ('PUSAT', 'CAB2');

end $$;

commit;

-- 5. Verify hasil
select b.branch_code, b.branch_name, b.city, b.is_active,
       (select count(*) from raw_transactions    r where r.branch_id = b.id) as trx,
       (select count(*) from journal_drafts      j where j.branch_id = b.id) as draft,
       (select count(*) from daily_cash_counts   c where c.branch_id = b.id) as cash_counts,
       (select count(*) from raw_bank_statements s where s.branch_id = b.id) as bank_stmts
from branches b
order by b.branch_code;