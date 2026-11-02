"""Create the ai_accounting database and run initial schema/seed.

Local (default):      python sql/create_db.py
Supabase / cloud:     DATABASE_URL="postgresql://...?sslmode=require" python sql/create_db.py

Sadar-remote: `CREATE DATABASE` hanya untuk host lokal — provider terkelola
(Supabase/Neon/Railway) tidak memberi hak itu, databasenya sudah ada.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from psycopg import connect
from psycopg.rows import dict_row

SQL_DIR = Path(__file__).resolve().parent
SETUP_SQL = SQL_DIR / "supabase_setup.sql"

DEFAULT_LOCAL_DSN = "postgresql://postgres@localhost:5432/ai_accounting"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


def _target_dsn() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_LOCAL_DSN)


def _is_local(dsn: str) -> bool:
    return (urlsplit(dsn).hostname or "") in _LOCAL_HOSTS


def _create_local_database(dsn: str) -> None:
    """Buat database kalau belum ada. Hanya untuk host lokal."""
    parts = urlsplit(dsn)
    dbname = parts.path.lstrip("/") or "ai_accounting"
    admin_dsn = f"postgresql://{parts.netloc}/postgres"

    with connect(admin_dsn, row_factory=dict_row) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if cur.fetchone():
                print(f"Database '{dbname}' sudah ada.")
                return
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", dbname):
                raise SystemExit(f"Nama database tidak valid: {dbname!r}")
            cur.execute(f"CREATE DATABASE {dbname} ENCODING 'UTF8'")
            print(f"Database '{dbname}' dibuat.")


def apply_schema(dsn: str) -> dict[str, int]:
    """Jalankan supabase_setup.sql dan kembalikan jumlah tabel + akun COA."""
    if not SETUP_SQL.exists():
        raise SystemExit(f"File SQL tidak ditemukan: {SETUP_SQL}")

    with connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(SETUP_SQL.read_text(encoding="utf-8"))
            rows = cur.fetchall() if cur.description else []

    counts = {r["jenis"]: int(r["jumlah"]) for r in rows} if rows else {}
    return counts


def create_database(with_password: bool = True) -> None:
    """Jalankan schema+seed ke target (DEFAULT_LOCAL_DSN atau env DATABASE_URL)."""
    dsn = _target_dsn()
    host = urlsplit(dsn).hostname or "(default)"
    print(f"Target: {host}")

    if _is_local(dsn):
        _create_local_database(dsn)
    else:
        print("Host remote terdeteksi — lewati CREATE DATABASE (dikelola provider).")

    counts = apply_schema(dsn)
    print("Schema + seed diterapkan.")

    tables = counts.get("tabel")
    coa = counts.get("coa")
    if coa is None:
        with connect(dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM chart_of_accounts")
                coa = cur.fetchone()["n"]
    print(f"COA: {coa} akun" + (f" | tabel: {tables}" if tables is not None else ""))


if __name__ == "__main__":
    sys.exit(0 if create_database() is None else 1)