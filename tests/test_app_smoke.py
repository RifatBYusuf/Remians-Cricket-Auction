import os

from streamlit.testing.v1 import AppTest


def test_public_demo_renders_without_exception_and_has_no_controls(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    app = AppTest.from_file("app.py").run(timeout=20)
    assert not app.exception
    assert len(app.button) == 0
    assert len(app.text_input) == 0
    assert len(app.selectbox) == 0
    assert len(app.number_input) == 0
    markup = "\n".join(element.value for element in app.markdown)
    assert "REMIANS AUSTRALIA" in markup
    assert "TEAM BALANCES" in markup
    assert "SOLD TO Team 2" in markup
    assert "৳825,000 BDT" in markup
    assert any("read-only visual preview" in caption.value for caption in app.caption)
