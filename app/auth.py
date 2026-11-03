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


def require_login() -> str:
    """Tampilkan halaman login sampai user berhasil masuk.

    Returns username (string) kalau sudah login (dashboard lanjut render).
    Memanggil ``st.stop()`` kalau belum login.
    """
    if is_logged_in():
        return st.session_state.get(_USERNAME_KEY, "Tim Dawend")


    expected = _secret("APP_PASSWORD")

    with st.container(key="login"):
        st.markdown(
            '<div class="brand"><div class="mark">D</div>'
            '<div><div class="name">Dawend</div>'
            '<div class="scope">Accounting Dashboard</div></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="login-h">Masuk</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="login-p">Dashboard kolaboratif untuk review jurnal dan '
            "operasional tim Dawend. Isi nama tim atau reviewer yang bertugas; "
            "setiap approve / reject dicatat atas nama tim.</p>",
            unsafe_allow_html=True,
        )

        if not expected:
            st.error(
                "**Dashboard terkunci.**\n\n"
                "`APP_PASSWORD` belum dikonfigurasi. Set di "
                "Streamlit Cloud → Settings → Secrets, atau environment "
                "variable `APP_PASSWORD` saat jalan lokal."
            )
            st.stop()

        with st.form("login_form", border=False, clear_on_submit=False):
            name = st.text_input(
                "Nama", value="Tim Dawend", autocomplete="name"
            )
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Masuk", type="primary", width="stretch")

        if submitted:
            if not name or not name.strip():
                st.error("Isi nama kamu dulu.")
            elif check_password(password, expected):
                st.session_state[_SESSION_KEY] = True
                st.session_state[_USERNAME_KEY] = name.strip()
                st.rerun()
            else:
                st.error("Password salah.")

        st.markdown(
            '<p class="login-f">Akses terbatas untuk tim Dawend. '
            "Hubungi admin kalau butuh akses.</p>",
            unsafe_allow_html=True,
        )

    st.stop()


def _render_logout_sidebar() -> None:
    with st.sidebar:
        st.divider()
        st.caption(f"Masuk sebagai **{st.session_state.get(_USERNAME_KEY, 'Tim Dawend')}**")
        if st.button("🚪 Logout", use_container_width=True):
            logout()
            st.rerun()
