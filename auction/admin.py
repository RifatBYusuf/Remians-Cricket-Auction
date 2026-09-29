from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

from auction.db import DatabaseError, require_admin_session, upload_asset
from auction.domain import AuctionError, validate_sale
from auction.images import slug, validate_image
from auction.ui import brand_header, money


def _flash(kind: str, text: str) -> None:
    st.session_state["flash"] = (kind, text)


def _show_flash() -> None:
    item = st.session_state.pop("flash", None)
    if item:
        getattr(st, item[0])(item[1])


def _error(exc: Exception) -> str:
    text = str(exc)
    for friendly in (
        "Administrator authorization required",
        "Final price must be greater than zero",
        "Player has already been sold",
        "Insufficient team funds",
        "There is no sale to undo",
        "Auction has already been created",
    ):
        if friendly.lower() in text.lower():
            return friendly + "."
    return "The change was not saved. Check your connection and input, then try again."


def login_screen(client: Any) -> bool:
    st.subheader("Administrator sign in")
    _, login_column, _ = st.columns([1, 2, 1])
    with login_column:
        st.caption("Use the Supabase Auth account that was added to `admin_users`.")
        with st.form("admin-login"):
            email = st.text_input("Email", autocomplete="email")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
    if submitted:
        try:
            st.session_state["admin_identity"] = require_admin_session(client, email.strip(), password)
            st.session_state["admin_client"] = client
            st.rerun()
        except DatabaseError as exc:
            st.error(str(exc))
    return False


def render_admin(client: Any) -> None:
    brand_header(admin=True)
    if "admin_identity" not in st.session_state:
        login_screen(client)
        return
    client = st.session_state.get("admin_client", client)
    who = st.session_state["admin_identity"]
    top_left, top_right = st.columns([4, 1])
    top_left.caption(f"Signed in as {who['email']} • All changes are enforced by Supabase authorization policies.")
    if top_right.button("Sign out", use_container_width=True):
        try:
            client.auth.sign_out()
        finally:
            for key in ("admin_identity", "admin_client", "pending_sale_request", "pending_undo_request"):
                st.session_state.pop(key, None)
            st.rerun()
    _show_flash()

    try:
        teams = client.table("teams").select("*").order("display_order").execute().data
        players = client.table("player_public").select("*").order("player_code").execute().data
        state_rows = client.table("auction_state").select("*").eq("singleton", True).execute().data
    except Exception:
        st.error("Could not load admin data from Supabase. No changes have been made.")
        return

    if not teams:
        st.warning("This project has no auction yet. Create it once to initialize exactly three teams at $1,000,000 AUD each.")
        if st.button("Create auction", type="primary"):
            try:
                client.rpc("create_auction").execute()
                _flash("success", "Auction created with three teams and $1,000,000 AUD per team.")
                st.rerun()
            except Exception as exc:
                st.error(_error(exc))
        return

    current_id = state_rows[0].get("current_player_id") if state_rows else None
    auction_tab, players_tab, teams_tab, history_tab, reset_tab = st.tabs(
        ["Auction control", "Players & cards", "Teams", "History & export", "Reset"]
    )
    with auction_tab:
        _auction_control(client, players, teams, current_id)
    with players_tab:
        _player_management(client, players)
    with teams_tab:
        _team_management(client, teams, players)
    with history_tab:
        _history(client)
    with reset_tab:
        _reset_auction(client)


def _set_current(client: Any, player_id: str) -> None:
    try:
        client.rpc("set_current_player", {"p_player_id": player_id}).execute()
        st.session_state.pop("pending_sale_request", None)
        st.rerun()
    except Exception as exc:
        st.error(_error(exc))


def _auction_control(client: Any, players: list[dict], teams: list[dict], current_id: str | None) -> None:
    st.subheader("Live auction control")
    if not players:
        st.info("Upload player cards before starting the auction.")
        return
    st.markdown("#### 1. Choose the player to show")
    st.caption("Select a player, then put that card on the audience display.")
    ids = [p["id"] for p in players]
    index = ids.index(current_id) if current_id in ids else 0
    select_col, _ = st.columns([3, 2])
    selected_id = select_col.selectbox(
        "Select player",
        ids,
        index=index,
        format_func=lambda pid: next(f"{p['player_code']} — {p['name']} [{p['status']}]" for p in players if p["id"] == pid),
    )
    prev_col, show_col, next_col, _ = st.columns([1, 1.4, 1, 4])
    if prev_col.button("← Previous", disabled=index <= 0):
        _set_current(client, ids[index - 1])
    if show_col.button("Show selected", type="primary"):
        _set_current(client, selected_id)
    if next_col.button("Next →", disabled=index >= len(ids) - 1):
        _set_current(client, ids[index + 1])

    current = next((p for p in players if p["id"] == current_id), None)
    if not current:
        st.info("Choose a player and select “Show selected” to put the card on the audience display.")
        return
    st.divider()
    st.markdown("#### 2. Record the auction result")
    st.markdown(f"**Current player:** {current['name']} · `{current['player_code']}`")
    summary_col, _ = st.columns([3, 2])
    with summary_col:
        c1, c2, c3 = st.columns(3)
        c1.metric("Status", current["status"].title())
        c2.metric("Role", current.get("playing_role") or "—")
        c3.metric("Base price", money(current.get("base_price")) if current.get("base_price") else "—")
    if current["status"] == "sold":
        st.success(f"Sold to {current['winning_team_name']} for {money(current['final_price'])}. This remains on the public display until you select another player.")
    else:
        sale_col, _ = st.columns([3, 2])
        with sale_col:
            with st.form("confirm-sale", clear_on_submit=False):
                team_id = st.selectbox(
                    "Winning team",
                    [t["id"] for t in teams],
                    format_func=lambda tid: next(f"{t['name']} — {money(t['budget_remaining'])} remaining" for t in teams if t["id"] == tid),
                )
                price = st.number_input("Final auction price (AUD)", min_value=1, step=1, value=int(current.get("base_price") or 1))
                confirm = st.form_submit_button("Confirm sale", type="primary")
        if confirm:
            team = next(t for t in teams if t["id"] == team_id)
            try:
                amount = validate_sale(current["status"], price, int(team["budget_remaining"]))
                request_id = st.session_state.setdefault("pending_sale_request", str(uuid4()))
                result = client.rpc(
                    "confirm_sale",
                    {"p_player_id": current["id"], "p_team_id": team_id, "p_final_price": amount, "p_request_id": request_id},
                ).execute().data
                st.session_state.pop("pending_sale_request", None)
                suffix = " (duplicate request safely ignored)" if result and result.get("duplicate") else ""
                _flash("success", f"Sale committed: {current['name']} → {team['name']} for {money(amount)}{suffix}.")
                st.rerun()
            except AuctionError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(_error(exc))
        if st.button("Mark player unsold"):
            try:
                client.rpc("mark_player_unsold", {"p_player_id": current["id"]}).execute()
                _flash("success", f"{current['name']} marked unsold. You can select and sell this player later.")
                st.rerun()
            except Exception as exc:
                st.error(_error(exc))
    st.divider()
    st.markdown("#### Need to correct a mistake?")
    st.caption("Undo only the most recently confirmed sale.")
    undo_confirm = st.checkbox("I understand this refunds the team and restores the player's previous status.")
    if st.button("Undo last sale", disabled=not undo_confirm):
        try:
            undo_request_id = st.session_state.setdefault("pending_undo_request", str(uuid4()))
            result = client.rpc("undo_last_sale", {"p_request_id": undo_request_id}).execute().data
            st.session_state.pop("pending_undo_request", None)
            _flash("success", f"Last sale undone. Refunded {money(result['refunded'])}.")
            st.rerun()
        except Exception as exc:
            st.error(_error(exc))


def _upload(client: Any, uploaded: Any, folder: str, key: str) -> str:
    content = uploaded.getvalue()
    ext, _ = validate_image(uploaded.name, uploaded.type, content)
    path = f"{folder}/{slug(key)}-{uuid4().hex[:12]}.{ext}"
    return upload_asset(client, "auction-assets", path, content, uploaded.type)


def _new_player_code() -> str:
    """Return a user-facing identifier without needing a database round trip."""
    return f"PLAYER-{uuid4().hex[:12].upper()}"


def _player_label(filename: str, player_code: str) -> str:
    """Use the card filename as an internal label when no details are entered."""
    return Path(filename).stem.strip() or player_code


def _player_management(client: Any, players: list[dict]) -> None:
    st.subheader("Upload Player Card")
    st.caption("Upload predesigned player cards. A unique player ID is assigned automatically to every card.")
    files = st.file_uploader(
        "Player card",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
    )
    if files and st.button("Upload Player Card", type="primary"):
        errors = []
        for file in files:
            try:
                validate_image(file.name, file.type, file.getvalue())
            except ValueError as exc:
                errors.append(f"{file.name}: {exc}")
        if errors:
            for message in errors:
                st.error(message)
            return

        try:
            assigned_codes = []
            for file in files:
                code = _new_player_code()
                path = _upload(client, file, "player-cards", code)
                client.table("players").insert(
                    {
                        "player_code": code,
                        "name": _player_label(file.name, code),
                        "card_image_path": path,
                    }
                ).execute()
                assigned_codes.append(code)
            noun = "card" if len(files) == 1 else "cards"
            _flash("success", f"Uploaded {len(files)} player {noun}. Assigned ID(s): {', '.join(assigned_codes)}")
            st.rerun()
        except Exception as exc:
            st.error(_error(exc))

    st.divider()
    st.subheader("Remove Player")
    if not players:
        st.info("No players have been uploaded yet.")
        return

    player_id = st.selectbox(
        "Player to remove",
        [player["id"] for player in players],
        format_func=lambda value: next(
            f"{player['name']} ({player['player_code']})"
            for player in players
            if player["id"] == value
        ),
    )
    selected = next(player for player in players if player["id"] == player_id)
    confirmed = st.checkbox(
        f"Permanently remove {selected['name']} ({selected['player_code']})",
        key=f"confirm-remove-player-{player_id}",
    )
    if st.button("Remove Player", disabled=not confirmed):
        try:
            client.table("players").delete().eq("id", player_id).execute()
            card_path = selected.get("card_image_path")
            if card_path:
                try:
                    client.storage.from_("auction-assets").remove([card_path])
                except Exception:
                    pass
            _flash("success", f"Removed {selected['name']} ({selected['player_code']}).")
            st.rerun()
        except Exception:
            st.error("This player could not be removed. Players already used in auction history must be retained.")


def _team_management(client: Any, teams: list[dict], players: list[dict]) -> None:
    st.subheader("Teams and purchased players")
    for team in teams:
        with st.expander(f"{team['name']} — {money(team['budget_remaining'])}", expanded=True):
            with st.form(f"team-{team['id']}"):
                name = st.text_input("Team name", value=team["name"])
                logo = st.file_uploader("Upload or replace logo", type=["png", "jpg", "jpeg", "webp"])
                save = st.form_submit_button("Save team")
            if save:
                if not name.strip():
                    st.error("Team name is required.")
                else:
                    try:
                        values = {"name": name.strip()}
                        if logo:
                            values["logo_path"] = _upload(client, logo, "team-logos", team["id"])
                        client.table("teams").update(values).eq("id", team["id"]).execute()
                        _flash("success", f"Saved {name.strip()}.")
                        st.rerun()
                    except Exception as exc:
                        st.error(_error(exc))
            bought = [p for p in players if p.get("winning_team_id") == team["id"] and p["status"] == "sold"]
            if bought:
                st.dataframe(
                    pd.DataFrame([{"Player ID": p["player_code"], "Player": p["name"], "Price (AUD)": p["final_price"]} for p in bought]),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.caption("No purchased players yet.")

#yoo 

def _history(client: Any) -> None:
    st.subheader("Transaction history")
    try:
        rows = client.table("transaction_history").select("*").order("sold_at", desc=True).execute().data
    except Exception:
        st.error("Could not load transaction history.")
        return
    if not rows:
        st.info("No sales have been recorded.")
        return
    frame = pd.DataFrame(rows)
    st.dataframe(frame, hide_index=True, use_container_width=True)
    st.download_button(
        "Export history as CSV",
        frame.to_csv(index=False).encode("utf-8"),
        f"auction-history-{datetime.now(timezone.utc).date().isoformat()}.csv",
        "text/csv",
    )


def _reset_auction(client: Any) -> None:
    st.subheader("Reset Auction")
    st.warning(
        "This permanently deletes every sale and all auction history, restores team budgets, "
        "marks every player available, and clears the live player display. Player cards and teams are kept."
    )
    confirmed = st.checkbox(
        "I understand this cannot be undone.",
        key="confirm-reset-auction",
    )
    if st.button("Reset Everything", type="primary", disabled=not confirmed):
        try:
            client.rpc("reset_auction").execute()
            st.session_state.pop("pending_sale_request", None)
            _flash("success", "Auction reset complete. All players and teams are back to their starting state.")
            st.rerun()
        except Exception as exc:
            st.error(_error(exc))
