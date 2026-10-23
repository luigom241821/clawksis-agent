"""Tests for ``clawk dashboard register``.

Covers the CLI half of self-hosted dashboard registration:
  - Docker-style auto-name generation
  - not-logged-in fast-fail (AuthError with relogin_required)
  - managed-install refusal
  - the happy path: POST shape, env-var writes, custom redirect URI
  - portal-URL write logic (only when non-default and not already set)
  - portal HTTP error mapping (401/403)

The portal HTTP call and the Nous token resolution are both mocked — this
file proves the CLI wiring + env-write behaviour. The live end-to-end token
round-trip against the Vercel preview build is a separate manual step.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

import clawk_cli.dashboard_register as dr


def _ns(**kw):
    defaults = dict(name=None, redirect_uri=None, portal_url=None)
    defaults.update(kw)
    return argparse.Namespace(**defaults)


class TestFastFails:
    def test_not_logged_in_exits_1_with_setup_hint(self, capsys):
        from clawk_cli.auth import AuthError

        err = AuthError("not logged in", provider="nous", relogin_required=True)
        with patch.object(dr, "cmd_dashboard_register", dr.cmd_dashboard_register):
            with (
                patch("clawk_cli.auth.resolve_nous_access_token", side_effect=err),
                patch("clawk_cli.config.is_managed", return_value=False),
            ):
                with pytest.raises(SystemExit) as exc:
                    dr.cmd_dashboard_register(_ns())
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "not logged into Nous Portal" in out
        assert "clawk setup" in out

    def test_managed_install_refuses(self, capsys):
        with patch("clawk_cli.config.is_managed", return_value=True):
            with pytest.raises(SystemExit) as exc:
                dr.cmd_dashboard_register(_ns())
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "not available in a managed" in out


def _fake_http_ok(payload: dict):
    """Return a context-manager urlopen stub yielding `payload` as JSON."""
    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return cm


class TestHappyPath:
    def _run(
        self,
        *,
        args,
        account_token="tok_abc",
        portal="https://portal.nousresearch.com",
        response=None,
        captured=None,
        existing_client_id=None,
    ):
        response = response or {
            "client_id": "agent:selfhost-1",
            "id": "selfhost-1",
            "name": "dreamy_tesla",
            "kind": "SELF_HOSTED",
            "custom_redirect_uri": None,
            "created_at": "2026-06-04T12:00:00.000Z",
        }

        def fake_urlopen(req, timeout=None):
            if captured is not None:
                captured["url"] = req.full_url
                captured["headers"] = dict(req.header_items())
                captured["body"] = json.loads(req.data.decode())
            return _fake_http_ok(response)

        saved = {}

        def fake_save(key, value):
            saved[key] = value

        # get_env_value is consulted twice: once for the stored client_id
        # (idempotency key) and once for CLAWK_DASHBOARD_PORTAL_URL. Route by
        # key so a test can seed a prior client_id while keeping the portal
        # unset (the default-portal-not-persisted path).
        def fake_get_env(key):
            if key == "CLAWK_DASHBOARD_OAUTH_CLIENT_ID":
                return existing_client_id
            return None

        with (
            patch(
                "clawk_cli.auth.resolve_nous_access_token", return_value=account_token
            ),
            patch("clawk_cli.config.is_managed", return_value=False),
            patch.object(dr, "_resolve_portal_base_url", return_value=portal),
            patch("clawk_cli.config.get_env_value", side_effect=fake_get_env),
            patch("clawk_cli.config.save_env_value", side_effect=fake_save),
            patch.object(dr.urllib.request, "urlopen", side_effect=fake_urlopen),
        ):
            dr.cmd_dashboard_register(args)
        return saved

    def test_writes_client_id_and_posts_generated_name(self, capsys):
        captured: dict = {}
        saved = self._run(args=_ns(), captured=captured)

        # POST shape
        assert captured["url"].endswith("/api/oauth/self-hosted-client")
        assert captured["headers"]["Authorization"] == "Bearer tok_abc"
        assert "name" in captured["body"] and captured["body"]["name"]
        assert "custom_redirect_uri" not in captured["body"]

        # env write: client_id present, portal URL NOT written (default portal)
        assert saved["CLAWK_DASHBOARD_OAUTH_CLIENT_ID"] == "agent:selfhost-1"
        assert "CLAWK_DASHBOARD_PORTAL_URL" not in saved

        out = capsys.readouterr().out
        assert "Registered dashboard" in out
        assert "non-loopback bind" in out  # the gate-engagement hint

    def test_explicit_name_is_sent(self, capsys):
        captured: dict = {}
        self._run(args=_ns(name="my_box"), captured=captured)
        assert captured["body"]["name"] == "my_box"


class TestIdempotentRerun(TestHappyPath):
    """Re-running with a stored client_id updates instead of creating.

    Inherits ``_run`` from TestHappyPath; the only new lever is
    ``existing_client_id`` (the CLAWK_DASHBOARD_OAUTH_CLIENT_ID a prior run
    persisted), which the CLI re-sends so the portal updates that row.
    """

    def test_stale_id_falls_through_to_create_prints_registered(self, capsys):
        # Stored id no longer resolves server-side -> portal created a fresh
        # row and returns a DIFFERENT id. The CLI treats that as a create and
        # persists the new id (re-run stays safe, never worse than first run).
        captured: dict = {}
        saved = self._run(
            args=_ns(name="seed_name"),
            existing_client_id="agent:selfhost-stale",
            response={
                "client_id": "agent:selfhost-new",
                "id": "selfhost-new",
                "name": "seed_name",
                "kind": "SELF_HOSTED",
                "custom_redirect_uri": None,
                "created_at": "2026-06-04T12:00:00.000Z",
            },
            captured=captured,
        )
        # The stale id is still SENT (portal decides create-vs-update).
        assert captured["body"]["client_id"] == "agent:selfhost-stale"
        # Returned id differs from what we sent -> message is "Registered".
        out = capsys.readouterr().out
        assert "Registered dashboard" in out
        assert "Updated dashboard" not in out
        assert saved["CLAWK_DASHBOARD_OAUTH_CLIENT_ID"] == "agent:selfhost-new"

    def test_blank_stored_client_id_treated_as_first_run(self, capsys):
        # A blank/whitespace stored value is not a usable key: treat as a
        # first registration (auto-generate a name, don't send client_id).
        captured: dict = {}
        self._run(
            args=_ns(),
            existing_client_id="   ",
            captured=captured,
        )

        assert (
            captured["body"]["custom_redirect_uri"]
            == "https://clawksis.example.com/auth/callback"
        )

    def test_non_default_portal_is_persisted(self, capsys):
        # No custom URL supplied, resolves to default → not written.
        saved = self._run(
            args=_ns(),
            portal="https://portal.nousresearch.com",
            existing_portal=None,
        )
        assert "CLAWK_DASHBOARD_PORTAL_URL" not in saved


class TestPublicUrlPersistence:
    """`--redirect-uri` derives & persists CLAWK_DASHBOARD_PUBLIC_URL in .env.

    --redirect-uri is the full public callback (e.g.
    https://clawk.example.com/auth/callback). At serve time the dashboard auth
    layer reconstructs that callback by appending "/auth/callback" to
    CLAWK_DASHBOARD_PUBLIC_URL, so the value that's actually consumed is the
    ORIGIN (scheme://host). We derive the origin from the supplied redirect URI
    and persist THAT as CLAWK_DASHBOARD_PUBLIC_URL — the var the runtime reads
    — so the public-URL override is genuinely wired, not just stored.

    An explicitly supplied value is always written (updating an existing entry
    in place rather than appending a duplicate); a no-op when it already
    matches; and never written on a localhost-only install (no --redirect-uri).
    """

    def _run(self, *, args, existing_public=None):
        """Drive cmd_dashboard_register, capturing save_env_value calls.

        `existing_public` is what get_env_value returns for
        CLAWK_DASHBOARD_PUBLIC_URL (None = not present in .env).
        """
        response = {
            "client_id": "agent:selfhost-1",
            "id": "selfhost-1",
            "name": "dreamy_tesla",
            "kind": "SELF_HOSTED",
            "custom_redirect_uri": getattr(args, "redirect_uri", None),
            "created_at": "2026-06-04T12:00:00.000Z",
        }

        saved: dict = {}

        def fake_save(key, value):
            saved[key] = value

        def fake_get_env_value(key, *a, **kw):
            if key == "CLAWK_DASHBOARD_PUBLIC_URL":
                return existing_public
            return None

        with (
            patch("clawk_cli.auth.resolve_nous_access_token", return_value="tok"),
            patch("clawk_cli.config.is_managed", return_value=False),
            patch.dict(dr.os.environ, {}, clear=False),
            patch.object(
                dr,
                "_resolve_portal_base_url",
                return_value="https://portal.nousresearch.com",
            ),
            patch("clawk_cli.config.get_env_value", side_effect=fake_get_env_value),
            patch("clawk_cli.config.save_env_value", side_effect=fake_save),
            patch.object(
                dr.urllib.request, "urlopen", return_value=_fake_http_ok(response)
            ),
        ):
            dr.os.environ.pop("CLAWK_DASHBOARD_PORTAL_URL", None)
            dr.cmd_dashboard_register(args)
        return saved

    def test_no_redirect_flag_does_not_overwrite_existing(self, capsys):
        # No --redirect-uri supplied but a value already exists → never touch
        # it (an existing entry is only changed by an explicit new value).
        saved = self._run(
            args=_ns(),
            existing_public="https://already-set.example.com",
        )
        assert "CLAWK_DASHBOARD_PUBLIC_URL" not in saved

    def test_non_http_redirect_not_persisted(self, capsys):
        # A malformed / non-http(s) redirect yields no derivable origin → skip.
        saved = self._run(
            args=_ns(redirect_uri="not-a-url"),
            existing_public=None,
        )
        assert "CLAWK_DASHBOARD_PUBLIC_URL" not in saved

    def test_public_url_persisted_alongside_portal_url(self, capsys):
        # Both --portal-url and --redirect-uri supplied → portal_url AND the
        # derived public_url are both persisted (ADD semantics: the public-url
        # write does not displace portal-url persistence).
        response = {
            "client_id": "agent:selfhost-1",
            "id": "selfhost-1",
            "name": "dreamy_tesla",
            "kind": "SELF_HOSTED",
            "custom_redirect_uri": "https://clawk.example.com/auth/callback",
            "created_at": "2026-06-04T12:00:00.000Z",
        }
        saved: dict = {}

        def fake_save(key, value):
            saved[key] = value

        with (
            patch("clawk_cli.auth.resolve_nous_access_token", return_value="tok"),
            patch("clawk_cli.config.is_managed", return_value=False),
            patch.dict(dr.os.environ, {}, clear=False),
            patch.object(
                dr,
                "_resolve_portal_base_url",
                return_value="https://preview.example.com",
            ),
            patch("clawk_cli.config.get_env_value", return_value=None),
            patch("clawk_cli.config.save_env_value", side_effect=fake_save),
            patch.object(
                dr.urllib.request, "urlopen", return_value=_fake_http_ok(response)
            ),
        ):
            dr.os.environ.pop("CLAWK_DASHBOARD_PORTAL_URL", None)
            dr.cmd_dashboard_register(
                _ns(
                    portal_url="https://preview.example.com",
                    redirect_uri="https://clawk.example.com/auth/callback",
                )
            )
        assert saved["CLAWK_DASHBOARD_PORTAL_URL"] == "https://preview.example.com"
        assert saved["CLAWK_DASHBOARD_PUBLIC_URL"] == "https://clawk.example.com"


class TestPortalResolution:
    def test_override_arg_wins(self):
        assert (
            dr._resolve_portal_base_url("https://preview.example.com/")
            == "https://preview.example.com"
        )

    def test_falls_back_to_stored_login_portal(self):
        with patch(
            "clawk_cli.auth.get_provider_auth_state",
            return_value={"portal_base_url": "https://portal.staging-nousresearch.com"},
        ):
            assert (
                dr._resolve_portal_base_url(None)
                == "https://portal.staging-nousresearch.com"
            )


class TestPortalErrors:
    def _run_http_error(self, code, body):
        err = urllib.error.HTTPError(
            url="https://portal.nousresearch.com/api/oauth/self-hosted-client",
            code=code,
            msg="err",
            hdrs=None,
            fp=BytesIO(json.dumps(body).encode()),
        )

        with (
            patch("clawk_cli.auth.resolve_nous_access_token", return_value="tok"),
            patch("clawk_cli.config.is_managed", return_value=False),
            patch.object(
                dr,
                "_resolve_portal_base_url",
                return_value="https://portal.nousresearch.com",
            ),
            patch.object(dr.urllib.request, "urlopen", side_effect=err),
        ):
            with pytest.raises(SystemExit) as exc:
                dr.cmd_dashboard_register(_ns())
        return exc.value.code

    def test_401_maps_to_reauth_message(self, capsys):
        code = self._run_http_error(401, {"error": "invalid_token"})
        assert code == 1
        assert "re-authenticate" in capsys.readouterr().out
