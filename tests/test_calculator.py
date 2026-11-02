"""Tests for deterministic calculation engine.

These tests pin the money math. The whole point of the architecture is that
AI never computes a number, so these must be exact to 2 decimals.
"""

from decimal import Decimal

import pytest

from app.calculator import ValidationError, calculate


def D(x):
    return Decimal(str(x))


def test_cash_sale_tax_exclusive():
    result = calculate(
        {
            "invoice_no": "INV-001",
            "business_date": "2026-11-01",
            "tax": {"pb1_rate": 0.10, "tax_inclusive": False},
            "lines": [
                {"item_name": "Kopi Susu", "qty": 2, "unit_price": 25000},
            ],
            "bill_discount": 0,
            "payments": [{"method": "CASH", "gross_amount": 55000}],
        }
    )
    assert result.gross_sales == D("50000.00")
    assert result.dpp == D("50000.00")
    assert result.tax == D("5000.00")
    assert result.total_due == D("55000.00")
    assert result.total_paid == D("55000.00")
    assert result.change_due == D("0.00")


def test_qris_sale_applies_mdr_and_net_settlement():
    result = calculate(
        {
            "invoice_no": "INV-002",
            "business_date": "2026-11-01",
            "tax": {"pb1_rate": 0.10, "tax_inclusive": False},
            "lines": [{"item_name": "Nasi Goreng", "qty": 1, "unit_price": 45000}],
            "bill_discount": 0,
            "payments": [{"method": "QRIS", "gross_amount": 49500, "mdr_rate": 0.007}],
        }
    )
    p = result.payments[0]
    assert p.mdr_fee == D("346.50")
    assert p.net_settlement == D("49153.50")
    assert p.change == D("0.00")
    assert result.total_due == D("49500.00")


def test_tax_inclusive_prices():
    result = calculate(
        {
            "invoice_no": "INV-003",
            "business_date": "2026-11-01",
            "tax": {"pb1_rate": 0.10, "tax_inclusive": True},
            "lines": [{"item_name": "Paket Hemat", "qty": 1, "unit_price": 55000}],
            "bill_discount": 0,
            "payments": [{"method": "CASH", "gross_amount": 55000}],
        }
    )
    assert result.dpp == D("50000.00")
    assert result.tax == D("5000.00")
    assert result.total_due == D("55000.00")


def test_bill_discount_reduces_dpp_and_tax():
    result = calculate(
        {
            "invoice_no": "INV-004",
            "business_date": "2026-11-01",
            "tax": {"pb1_rate": 0.10, "tax_inclusive": False},
            "lines": [{"item_name": "Spaghetti", "qty": 1, "unit_price": 50000}],
            "bill_discount": 5000,
            "payments": [{"method": "CASH", "gross_amount": 49500}],
        }
    )
    assert result.gross_sales == D("50000.00")
    assert result.bill_discount == D("5000.00")
    assert result.dpp == D("45000.00")
    assert result.tax == D("4500.00")
    assert result.total_due == D("49500.00")


def test_service_charge_is_separate_from_pb1():
    result = calculate(
        {
            "invoice_no": "INV-005",
            "business_date": "2026-11-01",
            "tax": {"pb1_rate": 0.10, "service_charge_rate": 0.05, "tax_inclusive": False},
            "lines": [{"item_name": "Dinner Set", "qty": 1, "unit_price": 100000}],
            "bill_discount": 0,
            "payments": [{"method": "CASH", "gross_amount": 115000}],
        }
    )
    assert result.dpp == D("100000.00")
    assert result.service_charge == D("5000.00")
    assert result.tax == D("10000.00")
    assert result.total_due == D("115000.00")


def test_cash_overpayment_produces_change():
    result = calculate(
        {
            "invoice_no": "INV-006",
            "business_date": "2026-11-01",
            "tax": {"pb1_rate": 0.10, "tax_inclusive": False},
            "lines": [{"item_name": "Kopi", "qty": 1, "unit_price": 50000}],
            "bill_discount": 0,
            "payments": [{"method": "CASH", "gross_amount": 100000}],
        }
    )
    assert result.total_due == D("55000.00")
    assert result.change_due == D("45000.00")
    assert result.payments[0].net_settlement == D("55000.00")


def test_split_payment_cash_and_qris():
    result = calculate(
        {
            "invoice_no": "INV-007",
            "business_date": "2026-11-01",
            "tax": {"pb1_rate": 0.10, "tax_inclusive": False},
            "lines": [{"item_name": "Family Pack", "qty": 1, "unit_price": 200000}],
            "bill_discount": 0,
            "payments": [
                {"method": "QRIS", "gross_amount": 100000, "mdr_rate": 0.007},
                {"method": "CASH", "gross_amount": 120000},
            ],
        }
    )
    # total due 220000; qris covers 100000, cash covers the remaining 120000
    cash = [p for p in result.payments if p.method == "CASH"][0]
    qris = [p for p in result.payments if p.method == "QRIS"][0]
    assert cash.change == D("0.00")
    assert cash.net_settlement == D("120000.00")
    assert qris.mdr_fee == D("700.00")
    assert qris.net_settlement == D("99300.00")
    assert result.total_paid == D("220000.00")
    assert result.change_due == D("0.00")


def test_underpayment_raises_validation_error():
    with pytest.raises(ValidationError) as exc:
        calculate(
            {
                "invoice_no": "INV-008",
                "business_date": "2026-11-01",
                "tax": {"pb1_rate": 0.10, "tax_inclusive": False},
                "lines": [{"item_name": "Kopi", "qty": 1, "unit_price": 50000}],
                "bill_discount": 0,
                "payments": [{"method": "CASH", "gross_amount": 50000}],
            }
        )
    assert "kurang" in str(exc.value).lower() or "underpaid" in str(exc.value).lower()


def test_line_discount_is_tracked():
    result = calculate(
        {
            "invoice_no": "INV-009",
            "business_date": "2026-11-01",
            "tax": {"pb1_rate": 0.10, "tax_inclusive": False},
            "lines": [
                {"item_name": "Kopi", "qty": 2, "unit_price": 25000, "line_discount": 5000},
            ],
            "bill_discount": 0,
            "payments": [{"method": "CASH", "gross_amount": 49500}],
        }
    )
    assert result.gross_sales == D("50000.00")
    assert result.line_discounts == D("5000.00")
    assert result.dpp == D("45000.00")
    assert result.tax == D("4500.00")