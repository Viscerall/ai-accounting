"""Deterministic journal mapping rules (fallback when Hermes is not configured)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.calculator import CalculationResult, PaymentSettlement
from app.config import settings


_D = Decimal
_ROUND = lambda x: _q2(x)


def _q2(x: Decimal) -> Decimal:
    """Quantize to 2 decimal places using Indonesian rounding (HALF_UP)."""
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class CoaAccount:
    id: int | None = None
    account_code: str = ""
    account_name: str = ""


@dataclass(frozen=True, slots=True)
class DraftItem:
    line_no: int
    account_code: str
    account_id: int | None
    debit: Decimal
    credit: Decimal
    description: str


@dataclass(frozen=True, slots=True)
class DraftLines:
    items: tuple[DraftItem, ...]
    total_debit: Decimal
    total_credit: Decimal
    reasoning: str
    confidence: Decimal


class MappingError(ValueError):
    pass


def build_draft(result: CalculationResult, coa: dict[str, CoaAccount]) -> DraftLines:
    """Build journal draft lines for a transaction.

    Args:
        result: CalculationResult from calculator.
        coa: Mapping of account_code → CoaAccount (retrieved from DB or LUT).

    Returns:
        DraftLines with exactly one row per line of the journal.

    Raises:
        MappingError if any required account is missing from coa.
    """
    lines_list: list[DraftItem] = []
    line_number = 0

    # Helper: get account, verify exists
    def _get_acct(code: str) -> CoaAccount:
        if code not in coa:
            raise MappingError(f"Account code '{code}' not found in COA. Please coa_with_seed() from DB.")
        return coa[code]

    # ---- revenue (dpp)
    acc_rev = _get_acct("4100")
    line_number += 1
    lines_list.append(
        DraftItem(
            line_no=line_number,
            account_code=acc_rev.account_code,
            account_id=acc_rev.id,
            debit=Decimal("0"),
            credit=_ROUND(result.dpp),
            description=f"Pokok penjualan ({result.invoice_no})",
        )
    )

    # ---- service charge (if > 0)
    if result.service_charge > 0:
        acc_sc = _get_acct("4110")
        line_number += 1
        lines_list.append(
            DraftItem(
                line_no=line_number,
                account_code=acc_sc.account_code,
                account_id=acc_sc.id,
                debit=Decimal("0"),
                credit=_ROUND(result.service_charge),
                description=f"Service charge ({result.invoice_no})",
            )
        )

    # ---- tax (PB1)
    if result.tax > 0:
        acc_tax = _get_acct("2100")
        line_number += 1
        lines_list.append(
            DraftItem(
                line_no=line_number,
                account_code=acc_tax.account_code,
                account_id=acc_tax.id,
                debit=Decimal("0"),
                credit=_ROUND(result.tax),
                description=f"Pajak PB1 ({result.invoice_no})",
            )
        )

    # ---- payments
    for pay in result.payments:
        if pay.method == "CASH":
            neutral_account: Literal["1100", "1120", "1121"] = "1100"
        elif pay.method == "QRIS":
            neutral_account = "1120"
        else:
            neutral_account = "1121"
        acc_net = _get_acct(neutral_account)

        # Net settlement line
        line_number += 1
        lines_list.append(
            DraftItem(
                line_no=line_number,
                account_code=acc_net.account_code,
                account_id=acc_net.id,
                debit=_ROUND(pay.net_settlement),
                credit=Decimal("0"),
                description=f"Settlement {pay.method} ({pay.acquirer or 'N/A'}) net",
            )
        )

        # MDR fee (if non-zero)
        if pay.mdr_fee > 0 and pay.method != "CASH":
            acc_mdr = _get_acct("6100")
            line_number += 1
            lines_list.append(
                DraftItem(
                    line_no=line_number,
                    account_code=acc_mdr.account_code,
                    account_id=acc_mdr.id,
                    debit=_ROUND(pay.mdr_fee),
                    credit=Decimal("0"),
                    description=f"Fee MDR {pay.method} {pay.acquirer or ''} ({pay.acquirer or 'N/A'})",
                )
            )

    # Balance check (stat sanity)
    total_debit = _ROUND(sum(i.debit for i in lines_list))
    total_credit = _ROUND(sum(i.credit for i in lines_list))

    if total_debit != total_credit or total_debit != result.total_due:
        # sanity — this shouldn't happen unless there's a bug
        raise MappingError(
            f"Draft not balanced: debit {total_debit} ≠ credit {total_credit} ≠ total_due {result.total_due}"
        )

    reasoning_parts = [
        f"Inv {result.invoice_no} ({result.business_date}):",
        f"Net sales DPP {result.dpp} → credit 4100",
    ]
    if result.service_charge > 0:
        reasoning_parts.append(f"Service charge {result.service_charge} → credit 4110")
    if result.tax > 0:
        reasoning_parts.append(f"Tax PB1 {result.tax} → credit 2100")
    reasoning_message = "; ".join(reasoning_parts)

    return DraftLines(
        items=tuple(lines_list),
        total_debit=total_debit,
        total_credit=total_credit,
        reasoning=reasoning_message,
        confidence=Decimal("0.85"),  # heuristic fallback confidence
    )