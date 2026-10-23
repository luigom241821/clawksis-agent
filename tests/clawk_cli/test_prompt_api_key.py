"""Tests for ``_prompt_api_key`` — the shared Keep/Replace/Clear menu used by
``clawk setup`` / ``clawk model`` when an API key already exists in ``.env``.

Regression coverage for #16394: the wizard used to silently skip the key prompt
when any value was present (even malformed junk), leaving users stuck.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from clawk_cli import main_provider_setup


@pytest.fixture
def profile_env(tmp_path, monkeypatch):

    home = tmp_path / ".clawksis"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("CLAWK_HOME", str(home))
    (home / ".env").write_text("")
    return home


def _pconfig(name="deepseek"):
    from clawk_cli.auth import PROVIDER_REGISTRY

    return PROVIDER_REGISTRY[name]


def _run_prompt(
    existing_key, choice, new_key="", provider_id="", pconfig_name="deepseek"
):
    """Invoke _prompt_api_key with mocked input()/getpass() responses."""
    from clawk_cli import main as m

    pconfig = _pconfig(pconfig_name)
    with (
        patch("builtins.input", return_value=choice),
        patch("clawk_cli.secret_prompt.masked_secret_prompt", return_value=new_key),
    ):
        return main_provider_setup._prompt_api_key(
            pconfig, existing_key, provider_id=provider_id
        )


def test_pool_only_key_does_not_offer_or_execute_clear(
    profile_env, monkeypatch, capsys
):
    from clawk_cli import main as m

    pconfig = _pconfig("deepseek")
    prompts = []

    def choose_clear(prompt):
        prompts.append(prompt)
        return "c"

    monkeypatch.setattr("builtins.input", choose_clear)
    with patch("clawk_cli.config.save_env_value") as save_env:
        key, abort = main_provider_setup._prompt_api_key(
            pconfig,
            "pool-secret",
            provider_id="deepseek",
            existing_source="credential_pool:deepseek",
        )

    assert key == "pool-secret"
    assert abort is False
    assert prompts and "[C]lear" not in prompts[0]
    assert "[K]eep / [R]eplace" in prompts[0]
    save_env.assert_not_called()
    assert "API key cleared" not in capsys.readouterr().out


# First-time entry ────────────────────────────────────────────────────────────


# Already configured — K / R / C ───────────────────────────────────────────────


def test_clear_wipes_env_and_aborts(profile_env):
    from clawk_cli.config import get_env_value, save_env_value

    save_env_value("DEEPSEEK_API_KEY", "sk-existing")
    save_env_value("OTHER_VAR", "keep-me")

    key, abort = _run_prompt(existing_key="sk-existing", choice="c")
    assert key == ""
    assert abort is True
    # Cleared, but sibling entries untouched.
    assert not get_env_value("DEEPSEEK_API_KEY")
    assert get_env_value("OTHER_VAR") == "keep-me"


# LM Studio no-auth placeholder ────────────────────────────────────────────────


def test_lmstudio_first_time_empty_uses_placeholder(profile_env):
    from clawk_cli.auth import LMSTUDIO_NOAUTH_PLACEHOLDER
    from clawk_cli.config import get_env_value

    key, abort = _run_prompt(
        existing_key="",
        choice="",
        new_key="",
        provider_id="lmstudio",
        pconfig_name="lmstudio",
    )
    assert key == LMSTUDIO_NOAUTH_PLACEHOLDER
    assert abort is False
    assert get_env_value("LM_API_KEY") == LMSTUDIO_NOAUTH_PLACEHOLDER


# Env-only keys (shell export) persist on Keep ────────────────────────────────
# Regression: a key exported in the shell was accepted as "configured ✓" but
# never written to .env, so the gateway (systemd) failed with "no API key was
# found" while the interactive terminal kept working.


def test_keep_persists_env_only_key(profile_env):
    """Keeping a key that is NOT in .env writes it there for the gateway."""
    from clawk_cli.config import load_env

    key, abort = _run_prompt(existing_key="sk-shell-export", choice="")
    assert (key, abort) == ("sk-shell-export", False)
    assert load_env().get("DEEPSEEK_API_KEY") == "sk-shell-export"


def test_replace_cancelled_persists_env_only_key(profile_env):
    """Cancelling Replace keeps the env-only key AND persists it."""
    from clawk_cli.config import load_env

    key, abort = _run_prompt(existing_key="sk-shell-export", choice="r", new_key="")
    assert (key, abort) == ("sk-shell-export", False)
    assert load_env().get("DEEPSEEK_API_KEY") == "sk-shell-export"


def test_keep_does_not_copy_bitwarden_key_to_disk(profile_env, monkeypatch):
    """Bitwarden-sourced secrets must never be written into .env."""
    from clawk_cli import env_loader
    from clawk_cli.config import load_env

    monkeypatch.setitem(env_loader._SECRET_SOURCES, "DEEPSEEK_API_KEY", "bitwarden")
    key, abort = _run_prompt(existing_key="sk-from-bitwarden", choice="")
    assert (key, abort) == ("sk-from-bitwarden", False)
    assert not load_env().get("DEEPSEEK_API_KEY")


def test_keep_already_persisted_key_is_silent(profile_env, capsys):
    """No 'Saved ... to' note when the kept key already lives in .env."""
    from clawk_cli.config import save_env_value

    save_env_value("DEEPSEEK_API_KEY", "sk-existing")
    capsys.readouterr()
    key, abort = _run_prompt(existing_key="sk-existing", choice="")
    assert (key, abort) == ("sk-existing", False)
    assert "Saved DEEPSEEK_API_KEY" not in capsys.readouterr().out
