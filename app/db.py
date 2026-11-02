"""PostgreSQL connection wrapper for ai_accounting.

Uses DATABASE_URL from .env or falls back to env vars.
"""

from pathlib import Path

from psycopg import connect, sql
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.config import settings
from app.mapping_rules import CoaAccount


def get_conn(*, row_factory=dict_row):
    """Get a fresh connection per thread (threadsafety='threaded')."""
    return connect(settings.database_url, row_factory=row_factory)


_HAS_BRANCHES: bool | None = None


def _has_branches_table() -> bool:
    """Detect if branches table exists (cached)."""
    global _HAS_BRANCHES
    if _HAS_BRANCHES is None:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM information_schema.tables WHERE table_name = 'branches'"
                    )
                    _HAS_BRANCHES = cur.fetchone() is not None
        except Exception:  # noqa: BLE001
            _HAS_BRANCHES = False
    return _HAS_BRANCHES


def _build_draft_select() -> str:
    """Return DRAFT_SELECT SQL adapted to whether branches table exists."""
    if _has_branches_table():
        return """
    SELECT d.id, d.draft_no, d.status, r.business_date, d.memo, d.ai_reasoning,
           d.ai_model, d.confidence, d.reviewed_by, d.reviewed_at, d.created_at,
           d.total_debit, d.total_credit, d.raw_transaction_id, d.branch_id,
           r.external_id, r.payload,
           b.branch_code, b.branch_name
      FROM journal_drafts d
      LEFT JOIN raw_transactions r ON r.id = d.raw_transaction_id
      LEFT JOIN branches b ON b.id = d.branch_id
"""
    # Legacy DB without branches table
    return """
    SELECT d.id, d.draft_no, d.status, r.business_date, d.memo, d.ai_reasoning,
           d.ai_model, d.confidence, d.reviewed_by, d.reviewed_at, d.created_at,
           d.total_debit, d.total_credit, d.raw_transaction_id, d.branch_id,
           r.external_id, r.payload,
           'PUSAT' AS branch_code, 'Cabang Utama' AS branch_name
      FROM journal_drafts d
      LEFT JOIN raw_transactions r ON r.id = d.raw_transaction_id
"""


def count_transactions(status: str | None = None) -> int:
    """Get count of raw_transactions by status."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            filters = []
            if status:
                filters.append("status = %(status)s")
            where = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(filters) if filters else sql.SQL("")
            cur.execute(
                sql.SQL("SELECT COUNT(*) FROM raw_transactions" + where),
                {"status": status} if status else {},
            )
            return cur.fetchone()["count"]


# --------------------------------------------------------------------------
# CABANG (multi-branch)
# --------------------------------------------------------------------------
def list_branches(active_only: bool = False) -> list[dict]:
    """Daftar cabang kafe. Kosong kalau tabel branches belum ada (DB belum di-migrasi)."""
    query = "SELECT id, branch_code, branch_name, city, is_active FROM branches"
    if active_only:
        query += " WHERE is_active = true"
    query += " ORDER BY branch_code"
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(query)
                return [dict(r) for r in cur.fetchall()]
            except Exception:  # noqa: BLE001 — DB lama tanpa tabel branches
                return []


def resolve_branch_id(cur, branch_code: str | None) -> int:
    """Kode cabang -> id. Fallback ke PUSAT (dibuat otomatis kalau belum ada)."""
    if not _has_branches_table():
        # Legacy database without branches table; rely on the column default 1
        return 1
    code = (branch_code or "PUSAT").strip().upper()
    try:
        cur.execute("SELECT id FROM branches WHERE branch_code = %(code)s", {"code": code})
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("SELECT id FROM branches WHERE branch_code = 'PUSAT'")
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute(
            "INSERT INTO branches (branch_code, branch_name) VALUES ('PUSAT', 'Cabang Utama') "
            "ON CONFLICT (branch_code) DO NOTHING"
        )
        cur.execute("SELECT id FROM branches WHERE branch_code = 'PUSAT'")
        return cur.fetchone()["id"]
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            "Tabel `branches` belum ada di database ini. "
            "Jalankan sql/003_branches.sql (lokal) atau paste supabase_setup.sql di Supabase SQL Editor."
        ) from exc



def ingest_transaction(payload: dict):
    """Insert a raw transaction and generate journal draft.

    Returns: (raw_txn_id, draft_id) on success.
    """
    invoice_no = payload.get("invoice_no", "").strip() or f"TMP-{__import__('uuid').uuid4().hex[:8]}"
    branch_raw = payload.get("branch")
    if isinstance(branch_raw, dict):
        branch_code = branch_raw.get("code") or branch_raw.get("branch_code")
    else:
        branch_code = payload.get("branch_code") or branch_raw
    with get_conn() as conn:
        with conn.cursor() as cur:
            branch_id = resolve_branch_id(cur, branch_code)
            # Insert raw_transactions. Invoice boleh sama antar-cabang, tetapi
            # tetap unik di dalam satu cabang.
            cur.execute(
                sql.SQL("""
                    INSERT INTO raw_transactions (external_id, branch_id, business_date, payload, status)
                    VALUES (%(external_id)s, %(branch_id)s, %(business_date)s, %(payload)s, 'RECEIVED')
                    ON CONFLICT (branch_id, external_id)
                    DO UPDATE SET payload = EXCLUDED.payload, ingested_at = NOW(), status = 'RECEIVED'
                    RETURNING id, business_date
                """),
                {
                    "external_id": invoice_no,
                    "branch_id": branch_id,
                    "business_date": payload.get("business_date"),
                    "payload": Json(payload),
                },
            )
            raw_txn = cur.fetchone()
            raw_txn_id = raw_txn["id"]

            # Insert journal_drafts header
            draft_no = f"DRAFT-{invoice_no[:14].upper()}-{__import__('uuid').uuid4().hex[:4].upper()}"
            cur.execute(
                sql.SQL("""
                    INSERT INTO journal_drafts (raw_transaction_id, branch_id, draft_no, journal_date, memo, total_debit, total_credit)
                    VALUES (%(raw_transaction_id)s, %(branch_id)s, %(draft_no)s,
                            (SELECT business_date FROM raw_transactions WHERE id = %(raw_transaction_id)s), %(memo)s, 0, 0)
                    RETURNING id
                """),
                {
                    "raw_transaction_id": raw_txn_id,
                    "branch_id": branch_id,
                    "draft_no": draft_no,
                    "memo": f"Generated for {invoice_no}",
                },
            )
            draft_id = cur.fetchone()["id"]

            # Insert journal_draft_items (deterministic)
            # Get all accounts from COA
            cur.execute("SELECT id, account_code, account_name FROM chart_of_accounts WHERE is_active = true")
            coa_rows = [dict(r) for r in cur.fetchall()]
            coa_map = {
                r["account_code"]: CoaAccount(id=r["id"], account_code=r["account_code"], account_name=r["account_name"])
                for r in coa_rows
            }

            # Run calculation locally
            from app.calculator import calculate
            from app.mapping_rules import build_draft

            result = calculate(payload)
            draft_lines = build_draft(result, coa_map)

            # Insert each line
            for item in draft_lines.items:
                cur.execute(
                    sql.SQL("""
                        INSERT INTO journal_draft_items (journal_draft_id, line_no, account_id, debit, credit, description)
                        VALUES (%(journal_draft_id)s, %(line_no)s, %(account_id)s, %(debit)s, %(credit)s, %(description)s)
                    """),
                    {
                        "journal_draft_id": draft_id,
                        "line_no": item.line_no,
                        "account_id": item.account_id,
                        "debit": item.debit,
                        "credit": item.credit,
                        "description": item.description,
                    },
                )

            # Update draft totals
            cur.execute(
                sql.SQL("UPDATE journal_drafts SET total_debit = %(total_debit)s, total_credit = %(total_credit)s WHERE id = %(draft_id)s"),
                {
                    "total_debit": draft_lines.total_debit,
                    "total_credit": draft_lines.total_credit,
                    "draft_id": draft_id,
                },
            )
            # Set status to PENDING
            cur.execute(
                sql.SQL("UPDATE journal_drafts SET status = 'PENDING' WHERE id = %(draft_id)s"),
                {"draft_id": draft_id},
            )

            conn.commit()
            return raw_txn_id, draft_id


def get_journal_drafts(status: str | None = None):
    """Get all journal drafts, optionally filtered by status."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            filters = []
            if status:
                filters.append("jd.status = %(status)s")
            where = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(filters) if filters else sql.SQL("")
            cur.execute(
                sql.SQL("""
                    SELECT
                        jd.id,
                        jd.draft_no,
                        jd.journal_date,
                        jd.memo AS review_memo,
                        jd.total_debit,
                        jd.total_credit,
                        jd.status,
                        jd.ai_reasoning,
                        jd.confidence,
                        jd.reviewed_by,
                        jd.reviewed_at,
                        jd.created_at,
                        rt.external_id,
                        rt.business_date,
                        rt.payload,
                        jsonb_agg(
                            jsonb_build_object(
                                'line_no', jdi.line_no,
                                'account_code', ca.account_code,
                                'account_id', ca.id,
                                'account_name', ca.account_name,
                                'debit', jdi.debit,
                                'credit', jdi.credit,
                                'description', jdi.description
                            )
                            ORDER BY jdi.line_no
                        ) AS items
                    FROM journal_drafts jd
                    LEFT JOIN raw_transactions rt ON jd.raw_transaction_id = rt.id
                    LEFT JOIN journal_draft_items jdi ON jd.id = jdi.journal_draft_id
                    LEFT JOIN chart_of_accounts ca ON jdi.account_id = ca.id
                    """ + where + sql.SQL(" GROUP BY jd.id, rt.external_id, rt.business_date ORDER BY jd.created_at DESC"))
                ,
                {"status": status} if status else {},
            )
            return [dict(r) for r in cur.fetchall()]


def update_journal_draft_status(draft_id: int, status: str, reviewer: str):
    """Update draft status to APPROVED, REJECTED, or SYNCED."""
    from app.calculator import calculate
    from app.mapping_rules import CoaAccount, build_draft

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Refresh calculation (in case payload changed)
            cur.execute("SELECT payload FROM raw_transactions WHERE id = (SELECT raw_transaction_id FROM journal_drafts WHERE id = %(draft_id)s)", {"draft_id": draft_id})
            row = cur.fetchone()
            if not row:
                raise ValueError(f"draft {draft_id} tidak memiliki raw_transactions")
            payload = row["payload"]

            # Recalculate
            result = calculate(payload)
            cur.execute("SELECT id, account_code, account_name FROM chart_of_accounts WHERE is_active = true")
            coa_rows = [dict(r) for r in cur.fetchall()]
            coa_map = {r["account_code"]: CoaAccount(id=r["id"], account_code=r["account_code"], account_name=r["account_name"]) for r in coa_rows}

            draft_lines = build_draft(result, coa_map)

            # Update totals & items
            cur.execute(
                sql.SQL("""
                    UPDATE journal_drafts
                    SET total_debit = %(total_debit)s,
                        total_credit = %(total_credit)s,
                        status = %(status)s,
                        reviewed_by = %(reviewer)s,
                        reviewed_at = NOW()
                    WHERE id = %(draft_id)s
                """),
                {
                    "total_debit": draft_lines.total_debit,
                    "total_credit": draft_lines.total_credit,
                    "status": status,
                    "reviewer": reviewer,
                    "draft_id": draft_id,
                },
            )

            # Upsert items (delete old then insert new)
            cur.execute("DELETE FROM journal_draft_items WHERE journal_draft_id = %(draft_id)s", {"draft_id": draft_id})
            for item in draft_lines.items:
                cur.execute(
                    sql.SQL("""
                        INSERT INTO journal_draft_items (journal_draft_id, line_no, account_id, debit, credit, description)
                        VALUES (%(journal_draft_id)s, %(line_no)s, %(account_id)s, %(debit)s, %(credit)s, %(description)s)
                    """),
                    {
                        "journal_draft_id": draft_id,
                        "line_no": item.line_no,
                        "account_id": item.account_id,
                        "debit": item.debit,
                        "credit": item.credit,
                        "description": item.description,
                    },
                )

            conn.commit()


# --------------------------------------------------------------------------
# Query helpers untuk dashboard & CLI
# --------------------------------------------------------------------------
DRAFT_SELECT = """
    SELECT d.id, d.draft_no, d.status, r.business_date, d.memo, d.ai_reasoning,
           d.ai_model, d.confidence, d.reviewed_by, d.reviewed_at, d.created_at,
           d.total_debit, d.total_credit, d.raw_transaction_id, d.branch_id,
           r.external_id, r.payload,
           'PUSAT' AS branch_code, 'Cabang Utama' AS branch_name
      FROM journal_drafts d
      LEFT JOIN raw_transactions r ON r.id = d.raw_transaction_id
"""


def _draft_select() -> str:
    """SQL draft lengkap; join branches hanya kalau tabelnya ada."""
    if not _has_branches_table():
        return DRAFT_SELECT
    return DRAFT_SELECT.replace(
        "'PUSAT' AS branch_code, 'Cabang Utama' AS branch_name",
        "b.branch_code, b.branch_name",
    ).replace(
        "LEFT JOIN raw_transactions r ON r.id = d.raw_transaction_id\n",
        "LEFT JOIN raw_transactions r ON r.id = d.raw_transaction_id\n      LEFT JOIN branches b ON b.id = d.branch_id\n",
    )


def _hydrate_draft(conn, row: dict) -> dict:
    """Lengkapi satu draft dengan items + payload."""
    draft = dict(row)
    draft["total_debit"] = float(draft["total_debit"] or 0)
    draft["total_credit"] = float(draft["total_credit"] or 0)
    draft["confidence"] = float(draft["confidence"] or 0)
    draft["external_id"] = draft.get("external_id") or "-"
    draft["branch_code"] = draft.get("branch_code") or "PUSAT"
    draft["branch_name"] = draft.get("branch_name") or "Cabang Utama"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.line_no, i.debit, i.credit, i.description,
                   c.account_code, c.account_name
              FROM journal_draft_items i
              LEFT JOIN chart_of_accounts c ON c.id = i.account_id
             WHERE i.journal_draft_id = %(draft_id)s
             ORDER BY i.line_no
            """,
            {"draft_id": draft["id"]},
        )
        draft["items"] = [
            {
                "line_no": r["line_no"],
                "account_code": r["account_code"],
                "account_name": r["account_name"],
                "debit": float(r["debit"] or 0),
                "credit": float(r["credit"] or 0),
                "description": r["description"],
            }
            for r in cur.fetchall()
        ]
    return draft


def list_drafts(status: str | None = None, limit: int = 500, branch_code: str | None = None) -> list[dict]:
    """List draft jurnal (default: semua status, terbaru dulu). branch_code=None -> semua cabang."""
    query = _draft_select()
    params: dict = {"limit": limit}
    filters = []
    if status:
        filters.append("d.status = %(status)s")
        params["status"] = status
    if branch_code and _has_branches_table():
        filters.append("d.branch_id = (SELECT id FROM branches WHERE branch_code = %(branch_code)s)")
        params["branch_code"] = branch_code
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY d.id DESC LIMIT %(limit)s"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [_hydrate_draft(conn, row) for row in rows]


def get_draft_by_id(draft_id: int) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_draft_select() + " WHERE d.id = %(draft_id)s", {"draft_id": draft_id})
            row = cur.fetchone()
        return _hydrate_draft(conn, row) if row else None


def set_draft_status(draft_id: int, status: str, reviewer: str = "nizar") -> None:
    """Ubah status satu draft (APPROVED / REJECTED / PENDING / SYNCED)."""
    if status not in {"PENDING", "APPROVED", "REJECTED", "SYNCED"}:
        raise ValueError(f"Status tidak dikenal: {status}")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE journal_drafts
                   SET status = %(status)s,
                       reviewed_by = %(reviewer)s,
                       reviewed_at = NOW()
                 WHERE id = %(draft_id)s
                """,
                {"status": status, "reviewer": reviewer, "draft_id": draft_id},
            )
        conn.commit()


def list_coa_rows() -> list[dict]:
    """Semua baris COA untuk tabel dashboard."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, account_code, account_name, account_type,
                       normal_balance, is_active, description
                  FROM chart_of_accounts
                 ORDER BY account_code
                """
            )
            return [dict(r) for r in cur.fetchall()]


def get_stats(branch_code: str | None = None) -> dict:
    """Ringkasan KPI per cabang; None berarti seluruh cabang."""
    where = ""
    params = {}
    if branch_code and _has_branches_table():
        where = " WHERE branch_id = (SELECT id FROM branches WHERE branch_code = %(branch_code)s)"
        params["branch_code"] = branch_code
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM raw_transactions" + where, params)
            raw = cur.fetchone()["n"]
            cur.execute(
                """
                SELECT status, COUNT(*) AS n, COALESCE(SUM(total_debit), 0) AS amount
                  FROM journal_drafts
                """
                + where
                + " GROUP BY status",
                params,
            )
            per_status = {r["status"]: r for r in cur.fetchall()}
    return {
        "raw_transactions": raw,
        "pending": per_status.get("PENDING", {}).get("n", 0),
        "approved": per_status.get("APPROVED", {}).get("n", 0),
        "rejected": per_status.get("REJECTED", {}).get("n", 0),
        "synced": per_status.get("SYNCED", {}).get("n", 0),
        "turnover": float(per_status.get("APPROVED", {}).get("amount", 0)),
    }


def reset_all() -> None:
    """Hapus semua transaksi & draft (COA tidak disentuh). Demo helper."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE journal_draft_items, journal_drafts, raw_transactions RESTART IDENTITY CASCADE"
            )
        conn.commit()


def recompute_draft(draft_id: int) -> dict:
    """Re-run rules engine on existing draft (items + totals), status -> PENDING."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.payload
                  FROM journal_drafts d
                  JOIN raw_transactions r ON r.id = d.raw_transaction_id
                 WHERE d.id = %(draft_id)s
                """,
                {"draft_id": draft_id},
            )
            row = cur.fetchone()
        if not row:
            raise ValueError(f"Draft {draft_id} tidak ditemukan")
        payload = row["payload"]
    from app.mapping_rules import build_draft
    new_lines = build_draft(payload)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE journal_drafts
                   SET total_debit = %(total_debit)s,
                       total_credit = %(total_credit)s,
                       status = 'PENDING',
                       reviewed_by = NULL,
                       reviewed_at = NULL
                 WHERE id = %(draft_id)s
                """,
                {
                    "total_debit": new_lines.total_debit,
                    "total_credit": new_lines.total_credit,
                    "draft_id": draft_id,
                },
            )
            cur.execute(
                "DELETE FROM journal_draft_items WHERE journal_draft_id = %(draft_id)s",
                {"draft_id": draft_id},
            )
            for item in new_lines.items:
                cur.execute(
                    """
                    INSERT INTO journal_draft_items (journal_draft_id, line_no, account_id, debit, credit, description)
                    VALUES (%(journal_draft_id)s, %(line_no)s, %(account_id)s, %(debit)s, %(credit)s, %(description)s)
                    """,
                    {
                        "journal_draft_id": draft_id,
                        "line_no": item.line_no,
                        "account_id": item.account_id,
                        "debit": item.debit,
                        "credit": item.credit,
                        "description": item.description,
                    },
                )
        conn.commit()
    return {"items": len(new_lines.items), "total_debit": float(new_lines.total_debit), "total_credit": float(new_lines.total_credit)}