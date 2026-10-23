"""Each web capability picks its own backend from the user's own keys (Clawksis is BYOK).

Upstream also offers a "Nous Subscription" row that routes a capability through the Nous Tool
Gateway. Clawksis never offers it: the picker rejects that row, the config payload carries no
``*_via_nous`` routing flags, and a per-capability pick writes the vendor's own backend name.
"""

import pytest


@pytest.fixture()
def client(monkeypatch, _isolate_clawk_home):
    starlette = pytest.importorskip("starlette.testclient")
    import clawk_state
    from clawk_constants import get_clawk_home
    from clawk_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app

    monkeypatch.setattr(clawk_state, "DEFAULT_DB_PATH", get_clawk_home() / "state.db")
    test_client = starlette.TestClient(app)
    test_client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return test_client


def test_web_capability_picks_use_own_keys_and_never_the_nous_gateway(
    client, monkeypatch
):
    from clawk_cli.config import load_config

    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-own-key")

    def put(expect=200, **body):
        resp = client.put("/api/tools/toolsets/web/provider", json=body)
        assert resp.status_code == expect, resp.text
        return client.get("/api/tools/toolsets/web/config").json()

    data = put(provider="Firecrawl", capability="search")
    assert load_config()["web"]["search_backend"] == "firecrawl"
    assert "search_via_nous" not in data and "extract_via_nous" not in data
    assert not [p for p in data["providers"] if p["name"] == "Nous Subscription"]

    put(expect=400, provider="Nous Subscription", capability="extract")
    put(expect=400, provider="Nous Subscription")
    web = load_config()["web"]
    assert web.get("search_backend") == "firecrawl"
    assert "nous" not in {
        web.get("backend"),
        web.get("search_backend"),
        web.get("extract_backend"),
    }
