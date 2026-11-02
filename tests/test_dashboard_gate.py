"""Test gerbang password dashboard lewat Streamlit AppTest (render sungguhan)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard.py"
_PASSWORD = "test-password-local-only"


def _run(monkeypatch, password=_PASSWORD):
    # Monkeypatch the secret source so test is isolated from local secrets.toml
    import app.auth as auth_mod

    def _fake_secret(name: str) -> str | None:
        if name == "APP_PASSWORD":
            return password
        return None

    monkeypatch.setattr(auth_mod, "_secret", _fake_secret)

    at = AppTest.from_file(DASHBOARD, default_timeout=60)
    at.run()
    return at


def test_fail_closed_when_password_not_configured(monkeypatch):
    """Tanpa APP_PASSWORD, dashboard harus menolak jalan — bukan terbuka."""
    at = _run(monkeypatch, password=None)

    assert not at.exception
    assert not at.session_state.get("_auth_ok")
    # Tidak boleh ada konten dashboard sama sekali
    assert not at.title, "dashboard ter-render padahal password belum di-set!"
    assert any("APP_PASSWORD" in str(e.value) for e in at.error)


def test_shows_login_form_and_hides_dashboard(monkeypatch):
    at = _run(monkeypatch)

    assert not at.exception
    assert not at.session_state.get("_auth_ok")
    # Dua field: Nama (text) + Password (password)
    assert len(at.text_input) == 2
    assert at.text_input[0].label == "Nama"
    assert at.text_input[1].label == "Password"
    assert "type: PASSWORD" in str(at.text_input[1].proto)
    # Dashboard (judul + metrics) belum boleh muncul
    assert not at.title
    assert not at.metric


def test_wrong_password_is_rejected(monkeypatch):
    at = _run(monkeypatch)
    at.text_input[0].set_value("Tim Dawend")   # name
    at.text_input[1].set_value("password-salah")  # password
    at.button[0].click().run()

    assert not at.session_state.get("_auth_ok")
    assert any("Password salah" in str(e.value) for e in at.error)
    assert not at.title


def test_empty_name_rejected(monkeypatch):
    """Nama kosong ditolak, password benar tetap gagal."""
    at = _run(monkeypatch)
    at.text_input[0].set_value("")      # name kosong
    at.text_input[1].set_value(_PASSWORD)
    at.button[0].click().run()

    assert not at.session_state.get("_auth_ok")
    assert any("Isi nama kamu" in str(e.value) for e in at.error)
    assert not at.title


def test_correct_password_unlocks(monkeypatch):
    at = _run(monkeypatch)
    at.text_input[0].set_value("Tester")
    at.text_input[1].set_value(_PASSWORD)
    at.button[0].click().run()

    assert not at.exception
    assert at.session_state["_auth_ok"] is True
    assert at.session_state["_auth_user"] == "Tester"
