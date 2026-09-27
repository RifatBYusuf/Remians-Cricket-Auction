from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

from auction.db import DatabaseError, require_admin_session, upload_asset
from auction.domain import AuctionError, parse_bdt, validate_sale
from auction.images import make_player_card, slug, validate_image
from auction.ui import brand_header, money


TEMPLATE = "player_id,name,playing_role,base_price\nRA-001,Sample Batter,Top-order batter,50000\nRA-002,Sample Bowler,Right-arm fast,40000\n"


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
        st.warning("This project has no auction yet. Create it once to initialize exactly three teams at ৳1,000,000 each.")
        if st.button("Create auction", type="primary"):
            try:
                client.rpc("create_auction").execute()
                _flash("success", "Auction created with three teams and ৳1,000,000 per team.")
                st.rerun()
            except Exception as exc:
                st.error(_error(exc))
        return

    current_id = state_rows[0].get("current_player_id") if state_rows else None
    auction_tab, players_tab, teams_tab, history_tab = st.tabs(
        ["Auction control", "Players & cards", "Teams", "History & export"]
    )
    with auction_tab:
        _auction_control(client, players, teams, current_id)
    with players_tab:
        _player_management(client, players)
    with teams_tab:
        _team_management(client, teams, players)
    with history_tab:
        _history(client)


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
        st.info("Add or import players before starting the auction.")
        return
    ids = [p["id"] for p in players]
    index = ids.index(current_id) if current_id in ids else 0
    selected_id = st.selectbox(
        "Select player",
        ids,
        index=index,
        format_func=lambda pid: next(f"{p['player_code']} — {p['name']} [{p['status']}]" for p in players if p["id"] == pid),
    )
    prev_col, show_col, next_col = st.columns([1, 2, 1])
    if prev_col.button("← Previous", disabled=index <= 0, use_container_width=True):
        _set_current(client, ids[index - 1])
    if show_col.button("Show selected player", type="primary", use_container_width=True):
        _set_current(client, selected_id)
    if next_col.button("Next →", disabled=index >= len(ids) - 1, use_container_width=True):
        _set_current(client, ids[index + 1])

    current = next((p for p in players if p["id"] == current_id), None)
    if not current:
        st.info("Choose a player and select “Show selected player” to put them on the audience display.")
        return
    st.divider()
    st.markdown(f"### {current['name']} · `{current['player_code']}`")
    c1, c2, c3 = st.columns(3)
    c1.metric("Status", current["status"].title())
    c2.metric("Role", current.get("playing_role") or "—")
    c3.metric("Base price", money(current.get("base_price")) if current.get("base_price") else "—")
    if current["status"] == "sold":
        st.success(f"Sold to {current['winning_team_name']} for {money(current['final_price'])}. This remains on the public display until you select another player.")
    else:
        with st.form("confirm-sale", clear_on_submit=False):
            team_id = st.selectbox(
                "Winning team",
                [t["id"] for t in teams],
                format_func=lambda tid: next(f"{t['name']} — {money(t['budget_remaining'])} remaining" for t in teams if t["id"] == tid),
            )
            price = st.number_input("Final auction price (BDT)", min_value=1, step=1, value=int(current.get("base_price") or 1))
            confirm = st.form_submit_button("Confirm sale", type="primary", use_container_width=True)
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
        if st.button("Mark player unsold", use_container_width=True):
            try:
                client.rpc("mark_player_unsold", {"p_player_id": current["id"]}).execute()
                _flash("success", f"{current['name']} marked unsold. You can select and sell this player later.")
                st.rerun()
            except Exception as exc:
                st.error(_error(exc))
    st.divider()
    st.markdown("#### Undo last sale")
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


def _player_management(client: Any, players: list[dict]) -> None:
    st.subheader("Player cards and details")
    upload_tab, create_tab, edit_tab, csv_tab = st.tabs(["Upload cards", "Create card", "Edit player", "CSV import"])
    with upload_tab:
        st.caption("Upload one or many predesigned cards. Every image is explicitly associated with a unique player ID and name.")
        files = st.file_uploader("Predesigned player cards", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
        if files:
            with st.form("multi-card-form"):
                mappings = []
                for number, file in enumerate(files, 1):
                    st.markdown(f"**{file.name}**")
                    a, b, c = st.columns([1, 2, 2])
                    code = a.text_input("Unique player ID", key=f"card-code-{number}-{file.name}")
                    name = b.text_input("Player name", key=f"card-name-{number}-{file.name}")
                    role = c.text_input("Playing role", key=f"card-role-{number}-{file.name}")
                    mappings.append((file, code, name, role))
                save = st.form_submit_button("Upload and save all cards", type="primary")
            if save:
                errors = []
                codes = [m[1].strip() for m in mappings]
                if any(not m[1].strip() or not m[2].strip() for m in mappings):
                    errors.append("Every card needs a unique player ID and player name.")
                if len(codes) != len(set(codes)):
                    errors.append("Player IDs must be unique within this upload.")
                for file, _, _, _ in mappings:
                    try:
                        validate_image(file.name, file.type, file.getvalue())
                    except ValueError as exc:
                        errors.append(str(exc))
                if errors:
                    for message in errors:
                        st.error(message)
                else:
                    try:
                        for file, code, name, role in mappings:
                            path = _upload(client, file, "player-cards", code)
                            client.table("players").upsert(
                                {"player_code": code.strip(), "name": name.strip(), "playing_role": role.strip(), "card_image_path": path},
                                on_conflict="player_code",
                            ).execute()
                        _flash("success", f"Saved {len(mappings)} player card(s).")
                        st.rerun()
                    except Exception as exc:
                        st.error(_error(exc))
    with create_tab:
        st.caption("Create a consistent player card from a photo and editable player details.")
        with st.form("create-card"):
            photo = st.file_uploader("Player photo", type=["png", "jpg", "jpeg", "webp"])
            code = st.text_input("Unique player ID")
            name = st.text_input("Player name")
            role = st.text_input("Playing role")
            base = st.number_input("Base price (optional, BDT; use 0 for none)", min_value=0, step=1)
            create = st.form_submit_button("Create and save player card", type="primary")
        if create:
            if not photo or not code.strip() or not name.strip() or not role.strip():
                st.error("Photo, unique player ID, name and playing role are required.")
            else:
                try:
                    validate_image(photo.name, photo.type, photo.getvalue())
                    photo_path = _upload(client, photo, "player-photos", code)
                    card = make_player_card(photo.getvalue(), name, role, int(base) or None)
                    card_path = upload_asset(client, "auction-assets", f"player-cards/{slug(code)}-{uuid4().hex[:12]}.png", card, "image/png")
                    client.table("players").insert(
                        {"player_code": code.strip(), "name": name.strip(), "playing_role": role.strip(), "base_price": int(base) or None, "photo_path": photo_path, "card_image_path": card_path}
                    ).execute()
                    _flash("success", f"Created player and card for {name.strip()}.")
                    st.rerun()
                except (ValueError, AuctionError) as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(_error(exc))
    with edit_tab:
        if not players:
            st.info("No players to edit yet.")
        else:
            pid = st.selectbox("Player to edit", [p["id"] for p in players], format_func=lambda x: next(f"{p['player_code']} — {p['name']}" for p in players if p["id"] == x))
            player = next(p for p in players if p["id"] == pid)
            with st.form("edit-player"):
                code = st.text_input("Unique player ID", value=player["player_code"])
                name = st.text_input("Player name", value=player["name"])
                role = st.text_input("Playing role", value=player.get("playing_role") or "")
                base = st.number_input("Base price (BDT; 0 for none)", min_value=0, step=1, value=int(player.get("base_price") or 0))
                replacement = st.file_uploader("Replace card image (optional)", type=["png", "jpg", "jpeg", "webp"])
                save = st.form_submit_button("Save player changes", type="primary")
            if save:
                if not code.strip() or not name.strip():
                    st.error("Player ID and name are required.")
                else:
                    try:
                        values = {"player_code": code.strip(), "name": name.strip(), "playing_role": role.strip(), "base_price": int(base) or None}
                        if replacement:
                            values["card_image_path"] = _upload(client, replacement, "player-cards", code)
                        client.table("players").update(values).eq("id", pid).execute()
                        _flash("success", "Player details saved.")
                        st.rerun()
                    except Exception as exc:
                        st.error(_error(exc))
    with csv_tab:
        st.download_button("Download example CSV template", TEMPLATE, "players-template.csv", "text/csv")
        uploaded = st.file_uploader("Player details CSV", type=["csv"])
        if uploaded and st.button("Validate and import CSV", type="primary"):
            rows, errors = _validate_csv(uploaded.getvalue())
            if errors:
                st.error("CSV was not imported. Fix these validation errors:")
                for message in errors:
                    st.write(f"• {message}")
            else:
                try:
                    client.table("players").upsert(rows, on_conflict="player_code").execute()
                    _flash("success", f"Imported {len(rows)} player(s). Existing matching player IDs were updated.")
                    st.rerun()
                except Exception as exc:
                    st.error(_error(exc))


def _validate_csv(content: bytes) -> tuple[list[dict], list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["File must use UTF-8 encoding."]
    try:
        reader = csv.DictReader(StringIO(text))
    except csv.Error as exc:
        return [], [f"Could not read CSV: {exc}"]
    required = {"player_id", "name", "playing_role", "base_price"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        return [], ["Header must include player_id, name, playing_role and base_price."]
    rows, errors, seen = [], [], set()
    for line, raw in enumerate(reader, 2):
        code, name = (raw.get("player_id") or "").strip(), (raw.get("name") or "").strip()
        role, base_text = (raw.get("playing_role") or "").strip(), (raw.get("base_price") or "").strip()
        if not code:
            errors.append(f"Row {line}: player_id is required.")
        elif code in seen:
            errors.append(f"Row {line}: duplicate player_id '{code}' in this file.")
        if not name:
            errors.append(f"Row {line}: name is required.")
        base = None
        if base_text:
            try:
                base = int(base_text)
                if base < 0:
                    raise ValueError
            except ValueError:
                errors.append(f"Row {line}: base_price must be a non-negative whole number or blank.")
        if code and name:
            rows.append({"player_code": code, "name": name, "playing_role": role, "base_price": base})
            seen.add(code)
    if not rows:
        errors.append("CSV contains no player rows.")
    return rows, errors


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
                    pd.DataFrame([{"Player ID": p["player_code"], "Player": p["name"], "Price (BDT)": p["final_price"]} for p in bought]),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.caption("No purchased players yet.")


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
