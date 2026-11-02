"""Tests for the deterministic journal mapping rules (the 'AI' fallback)."""

from decimal import Decimal

import pytest

from app.calculator import calculate
from app.mapping_rules import CoaAccount, MappingError, build_draft


def D(x):
    return Decimal(str(x))


COA = {
    "1100": CoaAccount(1, "1100", "Kas"),
    "1120": CoaAccount(2, "1120", "Piutang Settlement QRIS"),
    "1121": CoaAccount(3, "1121", "Piutang Settlement EDC"),
    "2100": CoaAccount(4, "2100", "Utang Pajak PB1"),
    "4110": CoaAccount(5, "4110", "Pendapatan Service Charge"),
    "4100": CoaAccount(6, "4100", "Pendapatan Penjualan"),
    "6100": CoaAccount(7, "6100", "Beban MDR / Payment Gateway"),
}


def _cash_sale():
    return calculate(
        {
            "invoice_no": "INV-C1",
            "business_date": "2026-11-01",
            "tax": {"pb1_rate": 0.10, "tax_inclusive": False},
            "lines": [{"item_name": "Kopi", "qty": 2, "unit_price": 25000}],
            "bill_discount": 0,
            "payments": [{"method": "CASH", "gross_amount": 55000}],
        }
    )


def _qris_sale():
    return calculate(
        {
            "invoice_no": "INV-Q1",
            "business_date": "2026-11-01",
            "tax": {"pb1_rate": 0.10, "tax_inclusive": False},
            "lines": [{"item_name": "Nasi Goreng", "qty": 1, "unit_price": 45000}],
            "bill_discount": 0,
            "payments": [{"method": "QRIS", "gross_amount": 49500, "mdr_rate": 0.007}],
        }
    )


def test_cash_sale_balances_and_hits_cash_account():
    draft = build_draft(_cash_sale(), COA)
    assert draft.total_debit == draft.total_credit
    assert draft.total_debit == D("55000.00")
    accounts = {i.account_code: i for i in draft.items}
    assert accounts["1100"].debit == D("55000.00")
    assert accounts["4100"].credit == D("50000.00")
    assert accounts["2100"].credit == D("5000.00")


def test_qris_sale_creates_clearing_and_mdr_lines():
    draft = build_draft(_qris_sale(), COA)
    assert draft.total_debit == draft.total_credit
    assert draft.total_debit == D("49500.00")
    accounts = {i.account_code: i for i in draft.items}
    assert accounts["1120"].debit == D("49153.50")   # net settlement
    assert accounts["6100"].debit == D("346.50")     # MDR expense
    assert accounts["4100"].credit == D("45000.00")
    assert accounts["2100"].credit == D("4500.00")   # PB1 = 10% of DPP 45000


def test_service_charge_goes_to_its_own_revenue_account():
    result = calculate(
        {
            "invoice_no": "INV-SC",
            "business_date": "2026-11-01",
            "tax": {"pb1_rate": 0.10, "service_charge_rate": 0.05, "tax_inclusive": False},
            "lines": [{"item_name": "Set", "qty": 1, "unit_price": 100000}],
            "bill_discount": 0,
            "payments": [{"method": "CASH", "gross_amount": 115000}],
        }
    )
    draft = build_draft(result, COA)
    accounts = {i.account_code: i for i in draft.items}
    assert accounts["4110"].credit == D("5000.00")
    assert accounts["4100"].credit == D("100000.00")
    assert draft.total_debit == draft.total_credit == D("115000.00")


def test_line_numbers_are_sequential():
    draft = build_draft(_qris_sale(), COA)
    assert [i.line_no for i in draft.items] == list(range(1, len(draft.items) + 1))


def test_missing_coa_account_raises():
    with pytest.raises(MappingError):
        build_draft(_qris_sale(), {"4100": COA["4100"]})


def test_reasoning_and_confidence_present():
    draft = build_draft(_qris_sale(), COA)
    assert draft.reasoning
    assert 0 < draft.confidence <= 1