"""Deterministic calculation engine for POS transactions.

This is the ONLY place where money math happens. AI never computes numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.config import settings


@dataclass(slots=True, frozen=True)
class PaymentSettlement:
    method: str
    acquirer: str | None
    gross_amount: Decimal
    mdr_rate: Decimal
    mdr_fee: Decimal
    net_settlement: Decimal
    change: Decimal


@dataclass(slots=True, frozen=True)
class CalculationResult:
    invoice_no: str
    business_date: str
    gross_sales: Decimal
    line_discounts: Decimal
    bill_discount: Decimal
    net_sales: Decimal
    dpp: Decimal
    service_charge: Decimal
    tax: Decimal
    total_due: Decimal
    total_paid: Decimal
    change_due: Decimal
    payments: tuple[PaymentSettlement, ...]


class ValidationError(ValueError):
    pass


def _q2(x: Decimal) -> Decimal:
    """Quantize to 2 decimal places using ROUND_HALF_UP (Indonesian standard)."""
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate(payload: dict) -> CalculationResult:
    """Compute exact amounts from a canonical transaction payload.

    Args:
        payload: Canonical format with keys:
            - invoice_no (str)
            - business_date (str, YYYY-MM-DD)
            - tax (dict):
                - pb1_rate (float) — e.g. 0.10
                - service_charge_rate (float, optional) — e.g. 0.05
                - tax_inclusive (bool, optional) — default False
            - lines (list[dict]):
                - item_name (str)
                - qty (int)
                - unit_price (float)
                - line_discount (float, optional)
            - bill_discount (float, optional)
            - payments (list[dict]):
                - method (str): "CASH" | "QRIS" | "DEBIT" | "CREDIT" | "EDC"
                - gross_amount (float): amount tendered/charged
                - mdr_rate (float, optional): MDR fee rate for non-cash
                - acquirer (str, optional)

    Returns:
        CalculationResult with all amounts quantized to 2dp.

    Raises:
        ValidationError if payments don't cover total_due.
    """
    # ---- parse lines
    lines = payload.get("lines", [])
    if not lines:
        raise ValidationError("Tidak ada item transaksi (lines kosong)")

    gross_sales = Decimal("0")
    line_discounts = Decimal("0")

    for line in lines:
        qty = Decimal(str(line.get("qty", 1)))
        unit_price = Decimal(str(line.get("unit_price", 0)))
        disc = Decimal(str(line.get("line_discount", 0)))
        gross_sales += qty * unit_price
        line_discounts += disc

    bill_discount = Decimal(str(payload.get("bill_discount", 0)))
    net_sales = _q2(gross_sales - line_discounts - bill_discount)

    # ---- tax & service charge
    tax_cfg = payload.get("tax", {})
    pb1_rate = Decimal(str(tax_cfg.get("pb1_rate", settings.default_pb1_rate)))
    sc_rate = Decimal(str(tax_cfg.get("service_charge_rate", settings.default_service_charge_rate)))
    tax_inclusive = tax_cfg.get("tax_inclusive", False)

    if tax_inclusive:
        divisor = Decimal("1") + pb1_rate + sc_rate
        dpp = _q2(net_sales / divisor)
        service_charge = _q2(dpp * sc_rate)
        tax = _q2(dpp * pb1_rate)
    else:
        dpp = net_sales
        service_charge = _q2(dpp * sc_rate)
        tax = _q2(dpp * pb1_rate)

    total_due = _q2(dpp + service_charge + tax)

    # ---- payments
    raw_payments = payload.get("payments", [])
    if not raw_payments:
        raise ValidationError("Tidak ada metode pembayaran (payments kosong)")

    non_cash_gross = Decimal("0")
    cash_gross = Decimal("0")
    settlements: list[PaymentSettlement] = []

    for p in raw_payments:
        method = p.get("method", "CASH").upper()
        gross = Decimal(str(p.get("gross_amount", 0)))
        mdr_rate = Decimal(str(p.get("mdr_rate", 0)))
        acquirer = p.get("acquirer")

        if method == "CASH":
            cash_gross += gross
            # mdr_rate ignored for cash; handled later when allocating change
            settlements.append(
                PaymentSettlement(
                    method="CASH",
                    acquirer=None,
                    gross_amount=gross,
                    mdr_rate=Decimal("0"),
                    mdr_fee=Decimal("0"),
                    net_settlement=Decimal("0"),  # filled after change calc
                    change=Decimal("0"),
                )
            )
        else:
            # QRIS, DEBIT, CREDIT, EDC
            non_cash_gross += gross
            mdr_fee = _q2(gross * mdr_rate)
            net = _q2(gross - mdr_fee)
            settlements.append(
                PaymentSettlement(
                    method=method,
                    acquirer=acquirer,
                    gross_amount=gross,
                    mdr_rate=mdr_rate,
                    mdr_fee=mdr_fee,
                    net_settlement=net,
                    change=Decimal("0"),
                )
            )

    # ---- validate payment coverage
    # cash applied = total_due - non_cash_gross
    cash_needed = total_due - non_cash_gross
    if cash_needed < 0:
        raise ValidationError(
            f"Total non-cash ({non_cash_gross:.2f}) melebihi total tagihan ({total_due:.2f})"
        )

    if cash_gross < cash_needed:
        raise ValidationError(
            f"Uang cash kurang: dibutuhkan {cash_needed:.2f}, diterima {cash_gross:.2f}"
        )

    cash_change = _q2(cash_gross - cash_needed)

    # finalize cash settlement net_settlement (gross - change)
    final_settlements = []
    for s in settlements:
        if s.method == "CASH":
            final_settlements.append(
                PaymentSettlement(
                    method="CASH",
                    acquirer=None,
                    gross_amount=s.gross_amount,
                    mdr_rate=Decimal("0"),
                    mdr_fee=Decimal("0"),
                    net_settlement=_q2(s.gross_amount - cash_change),
                    change=cash_change,
                )
            )
        else:
            final_settlements.append(s)

    total_paid = non_cash_gross + cash_needed
    total_paid = _q2(total_paid)

    return CalculationResult(
        invoice_no=payload.get("invoice_no", ""),
        business_date=payload.get("business_date", ""),
        gross_sales=_q2(gross_sales),
        line_discounts=_q2(line_discounts),
        bill_discount=_q2(bill_discount),
        net_sales=net_sales,
        dpp=dpp,
        service_charge=service_charge,
        tax=tax,
        total_due=total_due,
        total_paid=total_paid,
        change_due=cash_change,
        payments=tuple(final_settlements),
    )