"""Cron runs are viewable from the chat but read-only: ``prompt.submit`` refuses them (4009)."""

import threading

import pytest

from tui_gateway import server


@pytest.mark.parametrize(
    "session",
    [
        {"session_key": "20260101_abcdef", "source": "cron"},
        {"session_key": "cron_abc123_20260101_090000", "source": "tui"},
    ],
)
def test_prompt_submit_refuses_cron_sessions(monkeypatch, session):
    live = {**session, "history_lock": threading.Lock(), "running": False}
    monkeypatch.setitem(server._sessions, "cron-sid", live)

    resp = server.handle_request(
        {
            "id": "1",
            "method": "prompt.submit",
            "params": {"session_id": "cron-sid", "text": "hola"},
        }
    )

    assert resp["error"]["code"] == 4009, resp
    assert live["running"] is False
