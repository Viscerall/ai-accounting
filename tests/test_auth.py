"""Tests for the public dashboard password gate."""

from app.auth import check_password


def test_password_gate_accepts_matching_password():
    assert check_password("correct-horse", "correct-horse") is True


def test_password_gate_rejects_wrong_or_unconfigured_password():
    assert check_password("wrong", "correct-horse") is False
    assert check_password("correct-horse", None) is False
    assert check_password("", "correct-horse") is False
