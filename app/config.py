"""App configuration — loads .env and exposes default settings.

Prioritas sumber konfigurasi:
1. Environment variable (paling tinggi)
2. Streamlit secrets (`st.secrets`) — dipakai saat deploy di Streamlit Cloud
3. File `.env` lokal
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
# Jangan load `.env.example` sebagai environment aktif: placeholder di file itu
# bisa menimpa Streamlit Cloud secrets. Default ditangani oleh `_setting()`.


def _streamlit_secret(key: str) -> str | None:
    """Ambil nilai dari st.secrets kalau sedang jalan di Streamlit."""
    try:
        import streamlit as st

        value = st.secrets[key]
    except Exception:
        return None
    return str(value) if value else None


def _setting(key: str, default: str) -> str:
    return os.environ.get(key) or _streamlit_secret(key) or default


@dataclass(slots=True, frozen=True)
class Settings:
    database_url: str = _setting(
        "DATABASE_URL",
        "postgresql://postgres@localhost:5432/ai_accounting",
    )
    hermes_engine: str = _setting("HERMES_ENGINE", "rules")
    hermes_timeout: int = int(_setting("HERMES_PROMPT_TIMEOUT", "30"))
    default_pb1_rate: float = 0.10
    default_service_charge_rate: float = 0.0


settings = Settings()


def db_label() -> str:
    """Label aman (tanpa kredensial) untuk ditampilkan di UI."""
    url = settings.database_url
    tail = url.split("@")[-1] if "@" in url else url
    return tail.split("?")[0]

