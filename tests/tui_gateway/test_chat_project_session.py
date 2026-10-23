"""Chat projects (Clawksis): session.create stamps ``project_id``, the session row carries it once
persisted, and each turn applies the project's instruction overlay to the live agent."""

import sqlite3
from types import SimpleNamespace

from clawk_state import SessionDB
from tui_gateway import server


def _gateway_with_db(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAWK_HOME", str(tmp_path))
    db = SessionDB(db_path=tmp_path / "state.db")
    # The dashboard adds the column lazily (web_server._ensure_projects_schema); mirror that.
    db._conn.execute("ALTER TABLE sessions ADD COLUMN project_id TEXT")
    db._conn.commit()
    monkeypatch.setattr(server, "_get_db", lambda: db)
    monkeypatch.setattr(server, "_schedule_agent_build", lambda _sid: None)
    monkeypatch.setattr(server, "_schedule_session_cap_enforcement", lambda: None)
    monkeypatch.setattr(server, "_register_session_cwd", lambda _session: None)
    return db


def test_session_create_stamps_project_and_row_persists_it(monkeypatch, tmp_path):
    db = _gateway_with_db(monkeypatch, tmp_path)
    sid = None
    try:
        response = server.handle_request(
            {"id": "create", "method": "session.create",
             "params": {"source": "desktop", "project_id": "proj123"}}
        )
        assert "result" in response, response
        result = response["result"]
        sid, stored_id = result["session_id"], result["stored_session_id"]
        session = server._sessions[sid]
        assert session["project_id"] == "proj123"

        # Lazy draft: the row (and its project) lands with the first prompt's persist.
        assert server._persist_session_row_for_submit("rid", session) is None
        conn = sqlite3.connect(tmp_path / "state.db")
        try:
            row = conn.execute(
                "SELECT project_id FROM sessions WHERE id = ?", (stored_id,)
            ).fetchone()
        finally:
            conn.close()
        assert row == ("proj123",)
    finally:
        if sid:
            server._sessions.pop(sid, None)
        db.close()


def test_project_overlay_is_applied_once_and_keeps_other_overlays(monkeypatch):
    monkeypatch.setattr(
        server,
        "_project_instructions_block_for_session",
        lambda _session: f"{server._PROJECT_INSTRUCTIONS_BEGIN}\nbe brief\n{server._PROJECT_INSTRUCTIONS_END}",
    )
    agent = SimpleNamespace(ephemeral_system_prompt="persona overlay")
    session = {"agent": agent, "project_id": "proj123"}

    server._apply_project_instructions_to_session(session)
    server._apply_project_instructions_to_session(session)  # every turn re-applies: no duplicates

    prompt = agent.ephemeral_system_prompt
    assert prompt.startswith("persona overlay")
    assert prompt.count(server._PROJECT_INSTRUCTIONS_BEGIN) == 1
    assert "be brief" in prompt
