"""Password gate untuk dashboard publik.

Urutan prioritas sumber password:
1. Streamlit secrets (`st.secrets["APP_PASSWORD"]`) — dipakai di Streamlit Cloud
2. Environment variable `APP_PASSWORD` — dipakai untuk local dev / docker
3. File `.streamlit/secrets.toml` — otomatis dibaca Streamlit sebagai (1)

Kalau tidak ada sama sekali, dashboard menolak jalan (fail-closed),
bukan tiba-tiba terbuka untuk publik.
"""

from __future__ import annotations

import hmac
import os

import streamlit as st

_SESSION_KEY = "_auth_ok"
_USERNAME_KEY = "_auth_user"


def _secret(name: str) -> str | None:
    """Ambil secret dari st.secrets, fallback ke environment variable."""
    try:
        value = st.secrets[name]
        if value:
            return str(value)
    except Exception:
        pass
    value = os.environ.get(name)
    return str(value) if value else None


def check_password(entered: str, expected: str | None) -> bool:
    """Perbandingan constant-time; False kalau password belum dikonfigurasi."""
    if not expected or not entered:
        return False
    return hmac.compare_digest(entered.strip(), expected.strip())


def is_logged_in() -> bool:
    return bool(st.session_state.get(_SESSION_KEY))


def logout() -> None:
    st.session_state.pop(_SESSION_KEY, None)
    st.session_state.pop(_USERNAME_KEY, None)


def require_login() -> None:
    """Tampilkan halaman login sampai user berhasil masuk.

    Return None kalau sudah login (dashborad lanjut render).
    Memanggil ``st.stop()`` kalau belum login.
    """
    if is_logged_in():
        _render_logout_sidebar()
        return

    expected = _secret("APP_PASSWORD")

    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("## 🧾 AI Accounting")
        st.caption("Area terbatas — masukkan password untuk melanjutkan.")

        if not expected:
            st.error(
                "**Dashboard terkunci.**\n\n"
                "`APP_PASSWORD` belum dikonfigurasi. Set di "
                "Streamlit Cloud → Settings → Secrets, atau environment "
                "variable `APP_PASSWORD` saat jalan lokal."
            )
            st.stop()

        with st.form("login_form", clear_on_submit=False):
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Masuk", use_container_width=True, type="primary")

        if submitted:
            if check_password(password, expected):
                st.session_state[_SESSION_KEY] = True
                st.session_state[_USERNAME_KEY] = "nizar"
                st.rerun()
            else:
                st.error("Password salah.")

        st.caption("Akses hanya untuk pemilik. Semua aktivitas review tercatat atas nama `nizar`.")

    st.stop()


def _render_logout_sidebar() -> None:
    with st.sidebar:
        st.divider()
        st.caption(f"Masuk sebagai **{st.session_state.get(_USERNAME_KEY, 'nizar')}**")
        if st.button("🚪 Logout", use_container_width=True):
            logout()
            st.rerun()
