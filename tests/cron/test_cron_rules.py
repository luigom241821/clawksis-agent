"""Tests for the cron-handling rules wiring:

- inline-script auto-materialization (agent pasted script content into the
  path-only ``script`` field),
- the expanded ``_build_job_prompt`` guidance (language / natural tone /
  real-task / [SILENT]),
- ``stop_after_alert`` auto-pause after the first real delivery.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# --------------------------------------------------------------------------
# Inline-script auto-materialization
# --------------------------------------------------------------------------
class TestMaterializeInlineScript:
    def test_plain_path_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clawk_constants.get_clawk_home", lambda: tmp_path)
        from tools.cronjob_tools import _materialize_inline_script

        assert _materialize_inline_script("check.py", "job") == "check.py"
        assert _materialize_inline_script("sub/dir/run.sh", "job") == "sub/dir/run.sh"
        # Nothing should have been written for a plain path.
        assert not (tmp_path / "scripts").exists() or not list(
            (tmp_path / "scripts").glob("cron_*")
        )

    def test_shebang_bash_saved_as_sh(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clawk_constants.get_clawk_home", lambda: tmp_path)
        from tools.cronjob_tools import _materialize_inline_script

        content = "#!/usr/bin/env bash\nset -euo pipefail\necho hi\n"
        rel = _materialize_inline_script(content, "Meta WhatsApp active alert")

        assert rel.endswith(".sh")
        assert rel.startswith("cron_meta-whatsapp-active-alert_")
        saved = tmp_path / "scripts" / rel
        assert saved.is_file()
        assert saved.read_text(encoding="utf-8") == content

    def test_inline_python_without_shebang_saved_as_py(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clawk_constants.get_clawk_home", lambda: tmp_path)
        from tools.cronjob_tools import _materialize_inline_script

        content = "import json\nprint(json.dumps({'ok': True}))\n"
        rel = _materialize_inline_script(content, None)

        assert rel.endswith(".py")
        assert (tmp_path / "scripts" / rel).is_file()

    def test_detector(self):
        from tools.cronjob_tools import _looks_like_inline_script

        assert _looks_like_inline_script("#!/bin/bash\necho hi")
        assert _looks_like_inline_script("line one\nline two")
        assert not _looks_like_inline_script("check.py")
        assert not _looks_like_inline_script("   ")


# --------------------------------------------------------------------------
# Expanded cron guidance in _build_job_prompt
# --------------------------------------------------------------------------
class TestCronGuidance:
    def test_language_and_tone_and_task_clauses_present(self):
        from cron.scheduler import _build_job_prompt

        result = _build_job_prompt({"prompt": "Do the thing"})

        # Rule 1 (language), 2 (natural tone), 3 (real task), 4 ([SILENT]).
        assert "LANGUAGE" in result
        assert "Never default to English" in result
        assert "naturally" in result
        assert "REAL TASK" in result
        assert "[SILENT]" in result
        # Existing invariants must survive.
        assert "automatically delivered" in result
        assert "do NOT use send_message" in result
        assert "Do the thing" in result

    def test_user_profile_injected_when_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cron.scheduler._get_clawk_home", lambda: tmp_path)
        (tmp_path / "user.md").write_text(
            "Language: Spanish (LATAM). Name: Samuel.", encoding="utf-8"
        )
        from cron.scheduler import _build_job_prompt

        result = _build_job_prompt({"prompt": "go"})
        assert "USER PROFILE" in result
        assert "Samuel" in result

    def test_user_profile_skipped_when_job_opts_out(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cron.scheduler._get_clawk_home", lambda: tmp_path)
        (tmp_path / "user.md").write_text("Name: Samuel.", encoding="utf-8")
        from cron.scheduler import _build_job_prompt

        result = _build_job_prompt({"prompt": "go", "use_user_md": False})
        assert "## USER PROFILE" not in result
        assert "Samuel" not in result


# --------------------------------------------------------------------------
# Natural delivery header: "⏰ <job name>" instead of the robotic wrapper
# --------------------------------------------------------------------------
class TestNaturalDeliveryHeader:
    @staticmethod
    def _deliver(job, content):
        from cron.scheduler import _deliver_result
        from gateway.config import Platform

        pconfig = MagicMock()
        pconfig.enabled = True
        mock_cfg = MagicMock()
        mock_cfg.platforms = {Platform.TELEGRAM: pconfig}
        with (
            patch("gateway.config.load_gateway_config", return_value=mock_cfg),
            patch(
                "tools.send_message_tool._send_to_platform",
                new=AsyncMock(return_value={"success": True}),
            ) as send_mock,
        ):
            _deliver_result(job, content)
        send_mock.assert_called_once()
        return send_mock.call_args.kwargs.get("content") or send_mock.call_args[0][-1]

    def test_header_uses_job_name_without_robotic_wrapper(self):
        sent = self._deliver(
            {
                "id": "test-job",
                "name": "daily-report",
                "deliver": "origin",
                "origin": {"platform": "telegram", "chat_id": "123"},
            },
            "Here is today's summary.",
        )
        assert sent.startswith("⏰ daily-report\n\n")
        assert "Here is today's summary." in sent
        assert "(job_id:" not in sent
        assert "-------------" not in sent
        assert "To stop or manage this job" not in sent

    def test_header_falls_back_to_job_id(self):
        sent = self._deliver(
            {
                "id": "abc-123",
                "deliver": "origin",
                "origin": {"platform": "telegram", "chat_id": "123"},
            },
            "Output.",
        )
        assert sent.startswith("⏰ abc-123\n\n")

    def test_yuanbao_strips_natural_header(self):
        from plugins.platforms.yuanbao.adapter import MessageSender

        assert MessageSender.strip_cron_wrapper("⏰ daily\n\nbody text") == "body text"
        assert MessageSender.strip_cron_wrapper("plain reply") == "plain reply"


# --------------------------------------------------------------------------
# stop_after_alert: pause after the first real delivery
# --------------------------------------------------------------------------
class TestStopAfterAlert:
    """The tick body is split upstream; exercise the post-delivery hook directly."""

    def _delivery(self, response="Meta is back up ✅", **extra):
        from cron.scheduler import _RunDelivery, _is_cron_silence_response

        job = {
            "id": "alert-job",
            "name": "meta-up",
            "deliver": "origin",
            "origin": {"platform": "telegram", "chat_id": "123"},
        }
        job.update(extra)
        should_deliver = not _is_cron_silence_response(response)
        return _RunDelivery(
            job=job,
            success=True,
            error=None,
            should_deliver=should_deliver,
            delivery_attempted=should_deliver,
        )

    def test_pauses_after_real_delivery_when_flag_set(self):
        from cron.scheduler import _maybe_stop_after_alert

        with patch("cron.jobs.pause_job") as pause_mock:
            _maybe_stop_after_alert(self._delivery(stop_after_alert=True))

        pause_mock.assert_called_once()
        assert pause_mock.call_args.args[0] == "alert-job"

    def test_no_pause_without_flag(self):
        from cron.scheduler import _maybe_stop_after_alert

        with patch("cron.jobs.pause_job") as pause_mock:
            _maybe_stop_after_alert(self._delivery())

        pause_mock.assert_not_called()

    def test_no_pause_on_silent_even_with_flag(self):
        from cron.scheduler import _maybe_stop_after_alert

        with patch("cron.jobs.pause_job") as pause_mock:
            _maybe_stop_after_alert(
                self._delivery(response="[SILENT]", stop_after_alert=True)
            )

        pause_mock.assert_not_called()

    def test_no_pause_after_failed_delivery(self):
        from cron.scheduler import _maybe_stop_after_alert

        d = self._delivery(stop_after_alert=True)
        d.delivery_error = "telegram down"
        with patch("cron.jobs.pause_job") as pause_mock:
            _maybe_stop_after_alert(d)

        pause_mock.assert_not_called()


def test_format_job_surfaces_stop_after_alert_and_profile():
    from tools.cronjob_job_args import _format_job

    shown = _format_job({"id": "abc", "prompt": "x", "stop_after_alert": True, "profile": "work"})
    plain = _format_job({"id": "abc", "prompt": "x"})

    assert shown["stop_after_alert"] is True and shown["profile"] == "work"
    assert "stop_after_alert" not in plain and "profile" not in plain
