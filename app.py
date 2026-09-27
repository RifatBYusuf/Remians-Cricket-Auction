from __future__ import annotations

import streamlit as st

from auction.admin import render_admin
from auction.config import load_settings
from auction.db import DatabaseError, make_client, public_snapshot
from auction.ui import brand_header, demo_snapshot, inject_css, render_public


st.set_page_config(
    page_title="Remians Australia Cricket Auction",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()
settings = load_settings()
view = str(st.query_params.get("view", "public")).lower()

if view == "admin":
    try:
        client = st.session_state.get("admin_client") or make_client(settings)
        render_admin(client)
    except DatabaseError as exc:
        brand_header(admin=True)
        st.error(str(exc))
        st.code('SUPABASE_URL = "https://YOUR_PROJECT_REF.supabase.co"\nSUPABASE_ANON_KEY = "YOUR_ANON_KEY"')
else:
    brand_header()
    if settings.demo_mode:
        render_public(demo_snapshot())
        st.caption("DEMO_MODE is enabled: this is a read-only visual preview and is not connected to Supabase.")
    else:
        @st.fragment(run_every=1.5)
        def live_dashboard() -> None:
            try:
                client = make_client(settings)
                render_public(public_snapshot(client), client)
            except DatabaseError as exc:
                st.error(str(exc))
                st.info("The display will retry automatically. A failed connection never changes auction data.")

        live_dashboard()
