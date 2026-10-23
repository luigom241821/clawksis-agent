"""Tests for per-job profile support in cron jobs.



Covers data-layer validation/storage, cronjob tool plumbing, scheduler runtime

CLAWK_HOME scoping, and tick() serialization for profile jobs.

"""

from __future__ import annotations


import json

import os

from pathlib import Path


import pytest


@pytest.fixture()
def isolated_cron_profile_home(tmp_path, monkeypatch):
    """Create an isolated Clawksis root with a named profile and temp cron store."""

    root = tmp_path / "clawk-root"

    profile_home = root / "profiles" / "support"

    profile_home.mkdir(parents=True)

    # Upstream only resolves a named profile that carries an identity marker. The model lives in
    # the profile's own config: a fire routed to a sibling profile runs under multiplex secret
    # semantics, so the launch process's CLAWK_MODEL is deliberately invisible to it.
    (profile_home / "config.yaml").write_text(
        "model:\n  default: profile-model\n", encoding="utf-8"
    )

    (root / "cron").mkdir(parents=True)

    monkeypatch.setenv("CLAWK_HOME", str(root))

    monkeypatch.setattr("cron.jobs.CRON_DIR", root / "cron")

    monkeypatch.setattr("cron.jobs.JOBS_FILE", root / "cron" / "jobs.json")

    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", root / "cron" / "output")

    return root, profile_home


class TestNormalizeProfile:
    def test_none_and_empty_return_none(self, isolated_cron_profile_home):

        from cron.jobs import _normalize_profile

        assert _normalize_profile(None) is None

        assert _normalize_profile("") is None

        assert _normalize_profile("   ") is None

    def test_default_profile_is_valid_and_normalized(self, isolated_cron_profile_home):

        from cron.jobs import _normalize_profile

        assert _normalize_profile("Default") == "default"

    def test_named_profile_must_exist_and_is_normalized(
        self, isolated_cron_profile_home
    ):

        from cron.jobs import _normalize_profile

        assert _normalize_profile("Support") == "support"

    def test_invalid_profile_name_is_rejected(self, isolated_cron_profile_home):

        from cron.jobs import _normalize_profile

        with pytest.raises(ValueError):
            _normalize_profile("invalid!")

    def test_missing_named_profile_is_rejected(self, isolated_cron_profile_home):

        from cron.jobs import _normalize_profile

        with pytest.raises(FileNotFoundError):
            _normalize_profile("missing")


class TestCreateAndUpdateJobProfile:
    def test_create_stores_profile_id(self, isolated_cron_profile_home):

        from cron.jobs import create_job, get_job

        job = create_job(prompt="hello", schedule="every 1h", profile="Support")

        stored = get_job(job["id"])

        assert stored is not None

        assert stored["profile"] == "support"

    def test_create_without_profile_preserves_old_behaviour(
        self, isolated_cron_profile_home
    ):

        from cron.jobs import create_job, get_job

        job = create_job(prompt="hello", schedule="every 1h")

        stored = get_job(job["id"])

        assert stored is not None

        assert stored.get("profile") is None

    def test_create_accepts_explicit_default(self, isolated_cron_profile_home):

        from cron.jobs import create_job, get_job

        job = create_job(prompt="hello", schedule="every 1h", profile="default")

        stored = get_job(job["id"])

        assert stored is not None

        assert stored["profile"] == "default"

    def test_update_sets_and_clears_profile(self, isolated_cron_profile_home):

        from cron.jobs import create_job, get_job, update_job

        job = create_job(prompt="x", schedule="every 1h")

        update_job(job["id"], {"profile": "Support"})

        stored = get_job(job["id"])

        assert stored is not None

        assert stored["profile"] == "support"

        update_job(job["id"], {"profile": ""})

        stored = get_job(job["id"])

        assert stored is not None

        assert stored["profile"] is None

    def test_update_rejects_missing_profile(self, isolated_cron_profile_home):

        from cron.jobs import create_job, update_job

        job = create_job(prompt="x", schedule="every 1h")

        with pytest.raises(FileNotFoundError):
            update_job(job["id"], {"profile": "missing"})


class TestCronjobToolProfile:
    def test_create_and_list_with_profile(self, isolated_cron_profile_home):

        from tools.cronjob_tools import cronjob

        created = json.loads(
            cronjob(
                action="create",
                prompt="hi",
                schedule="every 1h",
                profile="Support",
            )
        )

        assert created["success"] is True

        assert created["job"]["profile"] == "support"

        listing = json.loads(cronjob(action="list"))

        assert listing["jobs"][0]["profile"] == "support"

    def test_update_clears_profile_with_empty_string(self, isolated_cron_profile_home):

        from tools.cronjob_tools import cronjob

        created = json.loads(
            cronjob(
                action="create",
                prompt="hi",
                schedule="every 1h",
                profile="Support",
            )
        )

        updated = json.loads(
            cronjob(action="update", job_id=created["job_id"], profile="")
        )

        assert updated["success"] is True

        assert "profile" not in updated["job"]

    def test_schema_advertises_profile(self):

        from tools.cronjob_tools import CRONJOB_SCHEMA

        assert "profile" in CRONJOB_SCHEMA["parameters"]["properties"]

        desc = CRONJOB_SCHEMA["parameters"]["properties"]["profile"]["description"]

        desc_lower = desc.lower()

        assert "clawk profile" in desc_lower

        assert "context-local" in desc_lower

        assert "subprocess" in desc_lower

        assert "temporarily sets clawk_home" not in desc_lower


class TestRunJobProfileContext:
    """Per-job ``profile`` through the current execution seams.

    Agent jobs no longer run inside the firing thread: ``run_job`` hands the fire to the gateway
    owner (``cron.scheduler_authority.run_canonical_job``), and the owner re-enters ``run_job``
    in-process under ``gateway.session_cron.current_execution()``. The ``cron_owner`` fixture swaps
    only the client transport for that real owner seam, so these tests cover the fork's profile
    switch (``_job_profile_context`` + ``_fire_secret_scope``) where production applies it.
    """

    @staticmethod
    def _install_agent_stubs(monkeypatch, observed: dict):

        import cron.scheduler as sched

        # The owner seam imports gateway.run, whose module-level dotenv load would otherwise be
        # recorded by the loader hook below; only per-run reloads are under test.
        import gateway.run

        def _snapshot(phase: str) -> None:
            from agent.runtime_cwd import scoped_session_cwd
            from agent.secret_scope import current_secret_scope_home
            from clawk_constants import get_clawk_home

            observed[f"env_home_during_{phase}"] = os.environ.get("CLAWK_HOME")
            observed[f"profile_env_only_during_{phase}"] = os.environ.get(
                "CLAWK_PROFILE_TEST_ONLY"
            )
            observed[f"profile_env_shared_during_{phase}"] = os.environ.get(
                "CLAWK_PROFILE_TEST_SHARED"
            )
            observed[f"clawk_home_during_{phase}"] = str(get_clawk_home())
            observed[f"scheduler_home_during_{phase}"] = str(sched._get_clawk_home())
            observed[f"secret_scope_home_during_{phase}"] = current_secret_scope_home()
            observed[f"session_cwd_during_{phase}"] = scoped_session_cwd()

        class FakeAgent:
            def __init__(self, **kwargs):
                _snapshot("init")
                observed["model"] = kwargs.get("model")
                observed["skip_context_files"] = kwargs.get("skip_context_files")

            def run_conversation(self, *_a, task_id=None, **_kw):
                from tools.terminal_tool import get_session_cwd

                _snapshot("run")
                observed["task_id"] = task_id
                observed["task_cwd_during_run"] = get_session_cwd(task_id)
                return {"final_response": "done", "messages": []}

            def get_activity_summary(self):

                return {"seconds_since_activity": 0.0}

            def interrupt(self, *_a, **_kw):
                pass

            def close(self):

                observed["closed"] = True

        monkeypatch.setattr("run_agent.AIAgent", FakeAgent)

        monkeypatch.setattr(
            "clawk_cli.runtime_provider.resolve_runtime_provider",
            lambda **_kw: {
                "provider": "test",
                "api_key": "test-key",
                "base_url": "http://test.local",
                "api_mode": "chat_completions",
            },
        )

        monkeypatch.setattr(
            "cron.scheduler_delivery._resolve_origin", lambda *_a, **_kw: None
        )
        monkeypatch.setattr("tools.mcp_tool_discovery.discover_mcp_tools", list)
        monkeypatch.setattr(sched, "_clawk_home", None)
        monkeypatch.setenv("CLAWK_CRON_TIMEOUT", "0")

        # run_job re-reads the env through clawk_cli.env_loader.load_clawk_dotenv
        # (not a bare dotenv.load_dotenv) so external secret sources are
        # re-resolved per run — hook that instead.

        from clawk_cli import env_loader

        def fake_load_clawk_dotenv(*, clawk_home=None, project_env=None):

            env_path = Path(clawk_home or ".") / ".env"

            observed.setdefault("dotenv_paths", []).append(str(env_path))

            return [env_path]

        monkeypatch.setattr(env_loader, "load_clawk_dotenv", fake_load_clawk_dotenv)

    @staticmethod
    def _job(job_id: str, **fields) -> dict:
        return {
            "id": job_id,
            "name": f"{job_id}-job",
            "prompt": "hi",
            "schedule_display": "manual",
            **fields,
        }

    def test_run_job_sets_and_restores_profile_home(
        self, isolated_cron_profile_home, monkeypatch, cron_owner
    ):

        import cron.scheduler as sched

        root, profile_home = isolated_cron_profile_home

        observed: dict = {}

        self._install_agent_stubs(monkeypatch, observed)

        success, _output, response, error = sched.run_job(
            self._job("abc", profile="support")
        )

        assert success is True, f"run_job failed: error={error!r} response={response!r}"

        assert response == "done"

        # config.yaml is read from the profile home.
        assert observed["model"] == "profile-model"

        assert observed["dotenv_paths"] == [str(profile_home.resolve() / ".env")]

        # The home switch is context-local: os.environ keeps the scheduler's root.
        assert observed["env_home_during_init"] == str(root)

        assert observed["env_home_during_run"] == str(root)

        assert observed["clawk_home_during_init"] == str(profile_home.resolve())

        assert observed["clawk_home_during_run"] == str(profile_home.resolve())

        assert observed["scheduler_home_during_init"] == str(profile_home.resolve())

        assert observed["scheduler_home_during_run"] == str(profile_home.resolve())

        # _fire_secret_scope: credentials come from the profile, not the scheduler home.
        assert observed["secret_scope_home_during_init"] == str(profile_home.resolve())

        assert observed["secret_scope_home_during_run"] == str(profile_home.resolve())

        assert observed["skip_context_files"] is True

        assert os.environ["CLAWK_HOME"] == str(root)

        assert sched._get_clawk_home() == root

    def test_profile_dotenv_environment_is_restored(
        self, isolated_cron_profile_home, monkeypatch, cron_owner
    ):

        from clawk_cli import env_loader

        import cron.scheduler as sched

        root, profile_home = isolated_cron_profile_home

        observed: dict = {}

        self._install_agent_stubs(monkeypatch, observed)

        monkeypatch.setenv("CLAWK_PROFILE_TEST_SHARED", "outer")

        monkeypatch.delenv("CLAWK_PROFILE_TEST_ONLY", raising=False)

        def fake_load_clawk_dotenv(*, clawk_home=None, project_env=None):

            env_path = Path(clawk_home or ".") / ".env"

            observed.setdefault("dotenv_paths", []).append(str(env_path))

            os.environ["CLAWK_PROFILE_TEST_SHARED"] = "profile-value"

            os.environ["CLAWK_PROFILE_TEST_ONLY"] = "profile-only"

            os.environ["CLAWK_CRON_TIMEOUT"] = "123"

            return [env_path]

        monkeypatch.setattr(env_loader, "load_clawk_dotenv", fake_load_clawk_dotenv)

        success, _output, _response, error = sched.run_job(
            self._job("env-profile", profile="support")
        )

        assert success is True, error

        assert observed["dotenv_paths"] == [str(profile_home.resolve() / ".env")]

        assert observed["profile_env_only_during_init"] == "profile-only"

        assert observed["profile_env_shared_during_init"] == "profile-value"

        assert observed["profile_env_only_during_run"] == "profile-only"

        assert observed["profile_env_shared_during_run"] == "profile-value"

        assert os.environ["CLAWK_PROFILE_TEST_SHARED"] == "outer"

        assert "CLAWK_PROFILE_TEST_ONLY" not in os.environ

        assert os.environ["CLAWK_CRON_TIMEOUT"] == "0"

        assert os.environ["CLAWK_HOME"] == str(root)

        assert sched._get_clawk_home() == root

    def test_no_agent_profile_uses_profile_scripts_dir_and_restores_env(
        self, isolated_cron_profile_home, monkeypatch
    ):

        import cron.scheduler as sched

        root, profile_home = isolated_cron_profile_home

        scripts_dir = profile_home / "scripts"

        scripts_dir.mkdir(parents=True)

        (scripts_dir / "print_home.py").write_text(
            "import os\nprint(os.environ.get('CLAWK_HOME', ''))\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(sched, "_clawk_home", None)

        job = {
            "id": "script1",
            "name": "profile-script",
            "profile": "support",
            "script": "print_home.py",
            "no_agent": True,
        }

        success, _doc, response, error = sched.run_job(job)

        assert success is True, error

        assert response.strip() == str(profile_home.resolve())

        assert os.environ["CLAWK_HOME"] == str(root)

        assert sched._get_clawk_home() == root

    def test_run_job_without_profile_leaves_clawk_home_untouched(
        self, isolated_cron_profile_home, monkeypatch, cron_owner
    ):

        import cron.scheduler as sched

        root, _profile_home = isolated_cron_profile_home

        observed: dict = {}

        self._install_agent_stubs(monkeypatch, observed)

        success, *_ = sched.run_job(self._job("noprof", profile=None))

        assert success is True

        assert Path(observed["clawk_home_during_init"]).resolve() == root.resolve()

        assert observed["dotenv_paths"] == [str(root.resolve() / ".env")]

        assert os.environ["CLAWK_HOME"] == str(root)

        assert sched._get_clawk_home() == root

    def test_run_job_falls_back_on_missing_runtime_profile(
        self, isolated_cron_profile_home, monkeypatch, cron_owner
    ):

        import cron.scheduler as sched

        root, _profile_home = isolated_cron_profile_home

        observed: dict = {}

        self._install_agent_stubs(monkeypatch, observed)

        # Should succeed with fallback, not raise

        success, _output, _response, error = sched.run_job(
            self._job("missing-profile", profile="missing")
        )

        assert success is True, f"run_job should fallback, not fail: error={error!r}"

        # Verify it used the scheduler's home, not the missing profile

        assert Path(observed["clawk_home_during_init"]).resolve() == root.resolve()

        assert os.environ["CLAWK_HOME"] == str(root)

        assert sched._get_clawk_home() == root


class TestTickProfilePartition:
    def test_profile_and_workdir_combined(
        self, isolated_cron_profile_home, monkeypatch, cron_owner
    ):
        """Both profile and workdir set — verify both are applied and restored."""

        import cron.scheduler as sched
        from agent.runtime_cwd import scoped_session_cwd
        from tools.terminal_tool import get_session_cwd

        root, profile_home = isolated_cron_profile_home

        observed: dict = {}

        TestRunJobProfileContext._install_agent_stubs(monkeypatch, observed)

        monkeypatch.delenv("TERMINAL_CWD", raising=False)

        fake_workdir = str(root / "myproject")

        (root / "myproject").mkdir()

        success, _output, _response, error = sched.run_job(
            TestRunJobProfileContext._job(
                "combo", profile="support", workdir=fake_workdir
            )
        )

        assert success is True, error

        assert observed["clawk_home_during_init"] == str(profile_home.resolve())

        # The workdir is a per-run scope (session cwd + task cwd), never process-global
        # TERMINAL_CWD, and it loads the project's context files.
        assert observed["skip_context_files"] is False

        assert observed["session_cwd_during_run"] == fake_workdir

        assert observed["task_cwd_during_run"] == fake_workdir

        assert os.environ.get("TERMINAL_CWD", "") != fake_workdir, (
            "TERMINAL_CWD should be restored after job"
        )

        assert get_session_cwd(observed["task_id"]) is None

        assert scoped_session_cwd() != fake_workdir

        assert os.environ["CLAWK_HOME"] == str(root)

        assert sched._get_clawk_home() == root

    def test_profile_jobs_run_sequentially(
        self, isolated_cron_profile_home, monkeypatch
    ):

        import threading

        import cron.scheduler as sched

        # Two profile jobs (both sequential) + one parallel job.

        profile_a = {"id": "a", "name": "A", "profile": "default"}

        profile_b = {"id": "b", "name": "B", "profile": "default"}

        parallel_job = {"id": "c", "name": "C", "profile": None}

        monkeypatch.setattr(
            sched, "get_due_jobs", lambda: [profile_a, profile_b, parallel_job]
        )

        monkeypatch.setattr(sched, "claim_job_for_fire", lambda *_a, **_kw: True)

        monkeypatch.setattr(sched, "_maybe_run_worktree_maintenance", lambda: None)

        calls: list[tuple[str, str]] = []

        order_lock = threading.Lock()

        def fake_run_job(job, **_kwargs):

            with order_lock:
                calls.append((job["id"], threading.current_thread().name))

            return True, "output", "response", None

        monkeypatch.setattr(sched, "run_job", fake_run_job)

        monkeypatch.setattr(sched, "save_job_output", lambda _jid, _o: None)

        monkeypatch.setattr(sched, "mark_job_run", lambda *_a, **_kw: None)

        monkeypatch.setattr(sched, "_deliver_result", lambda *_a, **_kw: None)

        n = sched.tick(verbose=False, sync=True)

        assert n == 3

        ids = [job_id for job_id, _thread_name in calls]

        # Sequential profile jobs preserve submission order relative to each

        # other (single-thread pool).

        assert ids.index("a") < ids.index("b")

        # Sequential (profile) jobs run on the persistent single-thread

        # cron-seq pool — NOT the main thread — so a long profile job never

        # blocks the ticker.  Parallel jobs run on the cron-parallel pool.

        for jid in ("a", "b"):
            seq_thread = next(t for job_id, t in calls if job_id == jid)

            assert seq_thread != threading.current_thread().name

            assert seq_thread.startswith("cron-seq"), seq_thread

        par_thread = next(t for job_id, t in calls if job_id == "c")

        assert par_thread.startswith("cron-parallel"), par_thread
