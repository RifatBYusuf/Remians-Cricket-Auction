from streamlit.testing.v1 import AppTest


def test_ended_display_replaces_player_and_waiting_messages():
    app = AppTest.from_string('''
from auction.ui import render_public
render_public({"state": {"ended": True}, "teams": [], "player": {"name": "Hidden player"}})
''').run()
    assert not app.exception
    markup = "\n".join(element.value for element in app.markdown)
    assert "Auction ended" in markup
    assert "WAITING FOR THE NEXT PLAYER" not in markup
    assert "Auction Ready" not in markup
    assert "Hidden player" not in markup


def test_end_button_available_without_players():
    app = AppTest.from_string('''
from auction.admin import _auction_control
_auction_control(None, [], [], None)
''').run()
    assert not app.exception
    assert app.button[0].label == "End Auction"
    assert not app.button[0].disabled


def test_end_button_updates_shared_state_and_is_disabled_after_ending():
    app = AppTest.from_string('''
import streamlit as st
from types import SimpleNamespace
from auction.admin import _auction_control
class Client:
    def table(self, table):
        assert table == "auction_state"
        return self
    def update(self, values):
        st.session_state["updated_values"] = values
        return self
    def eq(self, column, value):
        assert column == "singleton" and value is True
        return self
    def execute(self):
        st.session_state["ended"] = True
        return SimpleNamespace(data=[st.session_state["updated_values"]])
_auction_control(Client(), [], [], None, ended=st.session_state.get("ended", False))
''').run()
    app.button[0].click().run()
    assert not app.exception
    values = app.session_state["updated_values"]
    assert values["ended"] is True
    assert values["current_player_id"] is None
    assert app.button[0].disabled
