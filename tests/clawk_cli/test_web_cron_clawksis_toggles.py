"""Dashboard cron create carries the Clawksis per-job toggles (silent_notice / use_soul /
use_user_md / use_memory / fallback_models), an update keeps them, and the delivery-target
picker offers ``origin``."""

import asyncio

import pytest

pytest.importorskip("fastapi")


@pytest.fixture()
def client(monkeypatch, _isolate_clawk_home):
    from starlette.testclient import TestClient

    import clawk_state
    from clawk_cli import profiles
    from clawk_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app
    from clawk_constants import get_clawk_home

    home = get_clawk_home()
    (home / "cron").mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text("model: test-model\n", encoding="utf-8")
    monkeypatch.setattr(profiles, "_get_default_clawk_home", lambda: home)
    monkeypatch.setattr(profiles, "_get_profiles_root", lambda: home / "profiles")
    monkeypatch.setattr(clawk_state, "DEFAULT_DB_PATH", home / "state.db")
    test_client = TestClient(app)
    test_client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return test_client


def test_create_stores_toggles_and_update_keeps_them(client):
    created = client.post(
        "/api/cron/jobs",
        json={
            "prompt": "check the queue",
            "schedule": "every 1h",
            "silent_notice": False,
            "use_soul": False,
            "use_user_md": False,
            "use_memory": True,
            "fallback_models": ["openrouter:openai/gpt-5-mini"],
        },
    )
    assert created.status_code == 200, created.text
    job = created.json()
    assert (
        job["silent_notice"],
        job["use_soul"],
        job["use_user_md"],
        job["use_memory"],
    ) == (False, False, False, True)
    assert job["fallback_models"]

    updated = client.put(
        f"/api/cron/jobs/{job['id']}", json={"updates": {"name": "renamed"}}
    )
    assert updated.status_code == 200, updated.text
    after = updated.json()
    assert after["name"] == "renamed"
    assert (
        after["silent_notice"],
        after["use_soul"],
        after["use_user_md"],
        after["use_memory"],
    ) == (False, False, False, True)
    assert after["fallback_models"] == job["fallback_models"]


def test_create_defaults_match_the_cron_store(client):
    created = client.post(
        "/api/cron/jobs", json={"prompt": "ping", "schedule": "every 1h"}
    )
    assert created.status_code == 200, created.text
    job = created.json()
    assert (
        job["silent_notice"],
        job["use_soul"],
        job["use_user_md"],
        job["use_memory"],
    ) == (True, True, True, False)


def test_delivery_targets_offer_origin(monkeypatch):
    from clawk_cli.web_routers import cron as cron_router
    from cron import scheduler_delivery

    monkeypatch.setattr(scheduler_delivery, "cron_delivery_targets", list)

    ids = [
        t["id"] for t in asyncio.run(cron_router.get_cron_delivery_targets())["targets"]
    ]

    assert ids[0] == "local"
    assert "origin" in ids
