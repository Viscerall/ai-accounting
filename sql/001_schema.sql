-- AI Accounting Schema (Supabase-compatible PostgreSQL)
-- Run via DBeaver (or CLI): psql -U postgres -d ai_accounting -f 001_schema.sql

-- Helper: uuid-based ID for additional entities
create extension if not exists "uuid-ossp";

-- 1. CHART OF ACCOUNTS (Master COA)
create table chart_of_accounts (
  id bigserial primary key,
  account_code text unique not null check (char_length(account_code) <= 20),
  account_name text not null check (char_length(account_name) <= 200),
  account_type text not null check (account_type in ('ASSET','LIABILITY','EQUITY','REVENUE','COGS','EXPENSE')),
  normal_balance text not null check (normal_balance in ('DEBIT','CREDIT')),
  is_active boolean not null default true,
  description text,
  created_at timestamptz not null default now()
);

-- 2. RAW TRANSACTIONS (Staging)
create table raw_transactions (
  id bigserial primary key,
  source text not null default 'accurate_pos',
  external_id text unique not null,   -- invoice number / POS reference
  business_date date not null,
  payload jsonb not null,            -- original transaction payload
  status text not null default 'RECEIVED' check (status in ('RECEIVED','CALCULATED','DRAFTED','APPROVED','SYNCED','REJECTED','ERROR')),
  ingested_at timestamptz not null default now(),
  error_message text
);

-- 3. JOURNAL DRAFTS (AI产出)
create table journal_drafts (
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

-- 4. JOURNAL DRAFT ITEMS (Baris rincian)
create table journal_draft_items (
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

-- 5. DATA TABLES OPSIONAL (bank statements & cash counts)
create table raw_bank_statements (
  id bigserial primary key,
  bank_account text not null,
  statement_date date not null,
  amount numeric(18,2) not null,
  description text,
  transaction_id text,
  data jsonb,
  created_at timestamptz not null default now()
);

create table daily_cash_counts (
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

-- 6. AUDIT LOG
create table audit_log (
  id bigserial primary key,
  table_name text not null,
  record_id bigint,
  action text not null check (action in ('INSERT','UPDATE','DELETE')),
  old_values jsonb,
  new_values jsonb,
  actor text not null default 'system',
  created_at timestamptz not null default now()
);

-- Indexes untuk query cepat
create index idx_raw_transactions_status on raw_transactions(status);
create index idx_raw_transactions_business_date on raw_transactions(business_date);
create index idx_journal_drafts_status on journal_drafts(status);
create index idx_journal_draft_items_draft_id on journal_draft_items(journal_draft_id);
create index idx_audit_log_created_at on audit_log(created_at);