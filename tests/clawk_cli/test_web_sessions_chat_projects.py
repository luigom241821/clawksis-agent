"""GET /api/sessions tags rows with their chat project and filters by ``project_id``
(``none``/``null``/``unassigned`` = no project); /api/sessions/running reads the in-process
gateway's running sessions."""

import sqlite3

import pytest


@pytest.fixture
def client(monkeypatch, _isolate_clawk_home):
    from starlette.testclient import TestClient

    import clawk_state
    from clawk_cli import web_server_sessions
    from clawk_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app
    from clawk_constants import get_clawk_home

    monkeypatch.setattr(clawk_state, "DEFAULT_DB_PATH", get_clawk_home() / "state.db")
    web_server_sessions._last_auto_archive_check.clear()
    test_client = TestClient(app)
    test_client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return test_client


def _seed(db_path):
    from clawk_cli.web_server import _ensure_chat_projects_schema
    from clawk_state import SessionDB

    db = SessionDB(db_path=db_path)
    try:
        for sid in ("in-project", "loose"):
            db.create_session(sid, source="cli")
            db.append_message(sid, role="user", content="hi")
    finally:
        db.close()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_chat_projects_schema(conn)
        conn.execute(
            "INSERT INTO chat_projects (id, name, created_at, updated_at) VALUES ('p1', 'Alpha', 0, 0)"
        )
        conn.execute("UPDATE sessions SET project_id = 'p1' WHERE id = 'in-project'")
        conn.commit()
    finally:
        conn.close()


def test_sessions_are_tagged_and_filtered_by_project(client):
    from clawk_constants import get_clawk_home

    _seed(get_clawk_home() / "state.db")

    rows = {s["id"]: s for s in client.get("/api/sessions?limit=50").json()["sessions"]}
    assert rows["in-project"]["project_id"] == "p1"
    assert rows["in-project"]["project_name"] == "Alpha"
    assert rows["loose"]["project_id"] is None

    only = client.get("/api/sessions?limit=50&project_id=p1").json()
    assert [s["id"] for s in only["sessions"]] == ["in-project"]
    assert only["total"] == 1

    unassigned = client.get("/api/sessions?limit=50&project_id=unassigned").json()
    assert [s["id"] for s in unassigned["sessions"]] == ["loose"]


def test_sessions_list_without_projects_schema_tags_unassigned(client):
    from clawk_constants import get_clawk_home
    from clawk_state import SessionDB

    db = SessionDB(db_path=get_clawk_home() / "state.db")
    try:
        db.create_session("plain", source="cli")
        db.append_message("plain", role="user", content="hi")
    finally:
        db.close()

    response = client.get("/api/sessions?limit=50")

    assert response.status_code == 200, response.text
    assert response.json()["sessions"][0]["project_id"] is None


def test_running_sessions_come_from_the_tui_gateway(client, monkeypatch):
    from tui_gateway import server

    monkeypatch.setattr(server, "get_running_session_ids", lambda: ["sess-a"])

    assert client.get("/api/sessions/running").json() == {"running": ["sess-a"]}
