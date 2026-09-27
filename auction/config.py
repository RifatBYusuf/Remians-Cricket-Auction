from __future__ import annotations

from dataclasses import dataclass
import os

import streamlit as st


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str
    demo_mode: bool = False


def load_settings() -> Settings:
    def get(name: str, default: str = "") -> str:
        try:
            return str(st.secrets.get(name, os.getenv(name, default)))
        except Exception:
            return os.getenv(name, default)

    demo = get("DEMO_MODE", "false").lower() in {"1", "true", "yes"}
    return Settings(get("SUPABASE_URL"), get("SUPABASE_ANON_KEY"), demo)

