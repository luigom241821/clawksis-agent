"""Tests for the ChatCompletionsTransport."""

import json
from types import SimpleNamespace

import httpx
import pytest
from openai import OpenAI

from agent.transports import get_transport
from agent.transports.types import NormalizedResponse
from providers import get_provider_profile


@pytest.fixture
def transport():
    import agent.transports.chat_completions

    return get_transport("chat_completions")


class TestChatCompletionsBasic:
    def test_api_mode(self, transport):
        assert transport.api_mode == "chat_completions"

    def test_registered(self, transport):
        assert transport is not None

    @pytest.mark.parametrize("provider", ["openrouter"])
    def test_gpt56_ultra_uses_max_wire_effort(self, transport, provider):
        from providers import get_provider_profile

        profile = get_provider_profile(provider)
        kw = transport.build_kwargs(
            model="openai/gpt-5.6-sol",
            messages=[{"role": "user", "content": "Hi"}],
            tools=[],
            reasoning_config={"enabled": True, "effort": "ultra"},
            supports_reasoning=True,
            provider_profile=profile,
            provider_name=provider,
            base_url=profile.base_url,
        )
        assert kw["extra_body"]["reasoning"] == {"enabled": True, "effort": "max"}

    def test_convert_messages_strips_replayed_platform_message_id(self, transport):
        """SQLite replay exposes ``platform_message_id`` as ``message_id`` (JSONL transcript compat);
        the gateway stamps it on every user row from the admission id. It is delivery bookkeeping:
        the in-process CLI never sent it, so a resuming surface that let it through would send a
        different prefix for the same durable session and break the cache.
        """
        msgs = [{"role": "user", "content": "hi", "message_id": "adm-123"}]
        result = transport.convert_messages(msgs)
        assert "message_id" not in result[0]
        assert result[0]["content"] == "hi"

    def test_convert_messages_strips_timestamp(self, transport):
        """Internal per-message ``timestamp`` metadata (stamped by
        ``_apply_persist_user_message_override`` to preserve platform event
        time without embedding it in content, and persisted to the SQLite
        store) is not part of the OpenAI Chat Completions schema. Strict
        providers like Mistral / Fireworks-backed endpoints reject it with
        HTTP 422 'Extra inputs are not permitted, field: messages[N].timestamp'.
        Regression test for #47868.
        """
        msgs = [
            {"role": "user", "content": "hi", "timestamp": 1781976577.0},
        ]
        result = transport.convert_messages(msgs)
        assert "timestamp" not in result[0]
        assert result[0]["content"] == "hi"
        assert result[0]["role"] == "user"
        # Original list untouched (deepcopy-on-demand)
        assert msgs[0]["timestamp"] == 1781976577.0

    def test_convert_messages_strips_provider_replay_sidecars(self, transport):
        """Native-provider replay channels must not cross a provider boundary.

        ``bedrock_content_blocks`` intentionally remains in durable history so
        Bedrock can restore signed/reasoning blocks in their original order.
        Chat Completions providers do not recognize it, though, and strict
        endpoints reject unknown keys in ``messages`` with HTTP 400/422.
        """
        msgs = [
            {"role": "user", "content": "use a tool"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": "{}"},
                    }
                ],
                "anthropic_content_blocks": [{"thinking": "signed"}],
                "bedrock_content_blocks": [
                    {"reasoningContent": {"redactedContentBase64": "cmVhc29uaW5n"}},
                    {
                        "toolUse": {
                            "toolUseId": "call_1",
                            "name": "lookup",
                            "input": {},
                        }
                    },
                ],
            },
        ]

        result = transport.convert_messages(msgs, model="gpt-4o")

        assert "anthropic_content_blocks" not in result[1]
        assert "bedrock_content_blocks" not in result[1]
        assert result[1]["tool_calls"] == msgs[1]["tool_calls"]
        # Durable history remains available if this conversation returns to Bedrock.
        assert "anthropic_content_blocks" in msgs[1]
        assert "bedrock_content_blocks" in msgs[1]

    def test_convert_messages_strips_name_on_tool_results_only(self, transport):
        """``name`` is stripped from tool results only (schema-foreign there),
        preserved on user/assistant messages; the original list is untouched."""
        msgs = [
            {"role": "user", "content": "hi", "name": "sylvain"},
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "ok",
                "name": "execute_code",
            },
        ]
        result = transport.convert_messages(msgs)
        assert result[1] == {"role": "tool", "tool_call_id": "call_1", "content": "ok"}
        # Schema-valid on non-tool roles — untouched, including by identity.
        assert result[0]["name"] == "sylvain"
        assert msgs[1]["name"] == "execute_code"

    def test_convert_messages_no_copy_without_timestamp(self, transport):
        """A timestamp-free message list needs no sanitize pass and is
        returned by identity (preserves the deepcopy-on-demand contract)."""
        msgs = [{"role": "user", "content": "hi"}]
        assert transport.convert_messages(msgs) is msgs

    def test_convert_messages_strips_internal_scaffolding_markers(self, transport):
        """Clawksis-internal ``_``-prefixed markers must never reach the wire.

        The empty-response recovery path appends synthetic messages tagged
        with ``_empty_recovery_synthetic``; permissive providers ignore the
        unknown key, but strict gateways (opencode-go, codex.nekos.me)
        reject the request, poisoning every later turn in the session.
        """
        msgs = [
            {"role": "user", "content": "run the task"},
            {
                "role": "assistant",
                "content": "(empty)",
                "_empty_recovery_synthetic": True,
            },
            {"role": "user", "content": "continue", "_empty_recovery_synthetic": True},
            {
                "role": "assistant",
                "content": "done",
                "_thinking_prefill": True,
                "_empty_terminal_sentinel": True,
            },
        ]
        result = transport.convert_messages(msgs)
        for m in result:
            assert not any(k.startswith("_") for k in m), m
        # Visible content preserved
        assert result[1]["content"] == "(empty)"
        assert result[2]["content"] == "continue"
        # Original list untouched (deepcopy-on-demand)
        assert msgs[1]["_empty_recovery_synthetic"] is True

    def test_convert_messages_copy_on_write_for_dirty_history(self, transport):
        """Dirty provider metadata should not force a full-history deepcopy."""
        clean_tool_call = {
            "id": "call_clean",
            "type": "function",
            "function": {"name": "safe", "arguments": "{}"},
        }
        msgs = [
            {"role": "user", "content": "hi", "metadata": {"large": ["shared"]}},
            {
                "role": "assistant",
                "content": "ok",
                "tool_calls": [
                    clean_tool_call,
                    {
                        "id": "call_dirty",
                        "call_id": "call_dirty",
                        "response_item_id": "fc_dirty",
                        "extra_content": {"google": {"thought_signature": "SIG"}},
                        "type": "function",
                        "function": {"name": "t", "arguments": "{}"},
                    },
                ],
            },
        ]

        result = transport.convert_messages(msgs, model="gpt-4o")

        assert result is not msgs
        assert result[0] is msgs[0]
        assert result[1] is not msgs[1]
        assert result[1]["tool_calls"] is not msgs[1]["tool_calls"]
        assert result[1]["tool_calls"][0] is clean_tool_call
        assert result[1]["tool_calls"][1] is not msgs[1]["tool_calls"][1]
        assert "call_id" not in result[1]["tool_calls"][1]
        assert "response_item_id" not in result[1]["tool_calls"][1]
        assert "extra_content" not in result[1]["tool_calls"][1]
        assert "call_id" in msgs[1]["tool_calls"][1]
        assert "extra_content" in msgs[1]["tool_calls"][1]


class TestChatCompletionsBuildKwargs:
    def test_openrouter_provider_prefs(self, transport):
        from providers import get_provider_profile

        profile = get_provider_profile("openrouter")
        msgs = [{"role": "user", "content": "Hi"}]
        kw = transport.build_kwargs(
            model="gpt-4o",
            messages=msgs,
            provider_profile=profile,
            provider_preferences={"only": ["openai"]},
        )
        assert kw["extra_body"]["provider"] == {"only": ["openai"]}

    def test_openrouter_pareto_min_coding_score(self, transport):
        """Profile path: model=openrouter/pareto-code + score → plugins block."""
        from providers import get_provider_profile

        profile = get_provider_profile("openrouter")
        msgs = [{"role": "user", "content": "Hi"}]
        kw = transport.build_kwargs(
            model="openrouter/pareto-code",
            messages=msgs,
            provider_profile=profile,
            openrouter_min_coding_score=0.65,
        )
        assert kw["extra_body"]["plugins"] == [
            {"id": "pareto-router", "min_coding_score": 0.65}
        ]

    def test_openrouter_pareto_score_ignored_for_other_models(self, transport):
        """Score must not be emitted for any model other than openrouter/pareto-code."""
        from providers import get_provider_profile

        profile = get_provider_profile("openrouter")
        msgs = [{"role": "user", "content": "Hi"}]
        kw = transport.build_kwargs(
            model="anthropic/claude-sonnet-4.6",
            messages=msgs,
            provider_profile=profile,
            openrouter_min_coding_score=0.65,
        )
        assert "plugins" not in (kw.get("extra_body") or {})

    def test_openrouter_pareto_score_omitted_when_unset(self, transport):
        """No score → no plugins block (router uses its omission default = strongest coder)."""
        from providers import get_provider_profile

        profile = get_provider_profile("openrouter")
        msgs = [{"role": "user", "content": "Hi"}]
        kw = transport.build_kwargs(
            model="openrouter/pareto-code",
            messages=msgs,
            provider_profile=profile,
            openrouter_min_coding_score=None,
        )
        assert "plugins" not in (kw.get("extra_body") or {})

    def test_openrouter_pareto_score_out_of_range_dropped(self, transport):
        """Out-of-range scores must be silently dropped, not forwarded."""
        from providers import get_provider_profile

        profile = get_provider_profile("openrouter")
        msgs = [{"role": "user", "content": "Hi"}]
        for bad in (1.5, -0.1, "not-a-number"):
            kw = transport.build_kwargs(
                model="openrouter/pareto-code",
                messages=msgs,
                provider_profile=profile,
                openrouter_min_coding_score=bad,
            )
            assert "plugins" not in (kw.get("extra_body") or {}), f"bad={bad!r}"

    def test_openrouter_pareto_legacy_path(self, transport):
        """Legacy flag path (no profile loaded) must also emit the plugins block."""
        msgs = [{"role": "user", "content": "Hi"}]
        kw = transport.build_kwargs(
            model="openrouter/pareto-code",
            messages=msgs,
            is_openrouter=True,
            openrouter_min_coding_score=0.8,
        )
        assert kw["extra_body"]["plugins"] == [
            {"id": "pareto-router", "min_coding_score": 0.8}
        ]

    def test_reasoning_default(self, transport):
        msgs = [{"role": "user", "content": "Hi"}]
        kw = transport.build_kwargs(
            model="gpt-4o",
            messages=msgs,
            supports_reasoning=True,
        )
        assert kw["extra_body"]["reasoning"] == {"enabled": True, "effort": "medium"}

    def test_ollama_num_ctx(self, transport):
        from providers import get_provider_profile

        profile = get_provider_profile("custom")
        msgs = [{"role": "user", "content": "Hi"}]
        kw = transport.build_kwargs(
            model="llama3",
            messages=msgs,
            provider_profile=profile,
            ollama_num_ctx=32768,
        )
        assert kw["extra_body"]["options"]["num_ctx"] == 32768

    def test_custom_think_false(self, transport):
        from providers import get_provider_profile

        profile = get_provider_profile("custom")
        msgs = [{"role": "user", "content": "Hi"}]
        kw = transport.build_kwargs(
            model="qwen3",
            messages=msgs,
            provider_profile=profile,
            reasoning_config={"effort": "none"},
            base_url="http://127.0.0.1:11434/v1",
        )
        assert kw["extra_body"]["think"] is False

    def test_custom_omits_think_on_mistral(self, transport):
        from providers import get_provider_profile

        profile = get_provider_profile("custom")
        msgs = [{"role": "user", "content": "Hi"}]
        kw = transport.build_kwargs(
            model="mistral-small-latest",
            messages=msgs,
            provider_profile=profile,
            reasoning_config={"enabled": False, "effort": "none"},
            base_url="https://api.mistral.ai/v1",
        )
        assert kw.get("extra_body", {}).get("think") is None
        assert kw.get("reasoning_effort") == "none"

    def test_gemini_openai_compat_flash_reasoning_maps_to_nested_google_thinking_config(
        self, transport
    ):
        msgs = [{"role": "user", "content": "Hi"}]
        kw = transport.build_kwargs(
            model="gemini-3-flash-preview",
            messages=msgs,
            provider_name="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            reasoning_config={"enabled": True, "effort": "high"},
        )
        assert "thinking_config" not in kw["extra_body"]
        assert kw["extra_body"]["extra_body"]["google"]["thinking_config"] == {
            "include_thoughts": True,
            "thinking_level": "high",
        }

    def test_gemini_ultra_thinking_raises_first_request_max_tokens(self, transport):
        from agent.gemini_native_adapter import GEMINI_DEFAULT_MAX_OUTPUT_TOKENS
        from providers import get_provider_profile

        profile = get_provider_profile("gemini")
        kw = transport.build_kwargs(
            model="gemini-3.7-flash",
            messages=[{"role": "user", "content": "Hi"}],
            provider_profile=profile,
            provider_name="gemini",
            base_url=profile.base_url,
            max_tokens=4096,
            max_tokens_param_fn=lambda n: {"max_tokens": n},
            reasoning_config={"enabled": True, "effort": "ultra"},
        )
        assert kw["max_tokens"] == GEMINI_DEFAULT_MAX_OUTPUT_TOKENS
        assert kw["extra_body"]["thinking_config"]["thinkingLevel"] == "high"

        # Also verify gemini-3.8-flash gets headroom and correct thinking level
        kw38 = transport.build_kwargs(
            model="gemini-3.8-flash",
            messages=[{"role": "user", "content": "Hi"}],
            provider_profile=profile,
            provider_name="gemini",
            base_url=profile.base_url,
            max_tokens=4096,
            max_tokens_param_fn=lambda n: {"max_tokens": n},
            reasoning_config={"enabled": True, "effort": "medium"},
        )
        assert kw38["max_tokens"] == GEMINI_DEFAULT_MAX_OUTPUT_TOKENS
        assert kw38["extra_body"]["thinking_config"]["thinkingLevel"] == "medium"

    def test_gemini_without_thinking_keeps_explicit_max_tokens(self, transport):
        from providers import get_provider_profile

        profile = get_provider_profile("gemini")
        kw = transport.build_kwargs(
            model="gemini-3.7-flash",
            messages=[{"role": "user", "content": "Hi"}],
            provider_profile=profile,
            provider_name="gemini",
            base_url=profile.base_url,
            max_tokens=4096,
            max_tokens_param_fn=lambda n: {"max_tokens": n},
        )
        assert kw["max_tokens"] == 4096

    def test_omit_temperature(self, transport):
        """Omit temperature is set via ProviderProfile with OMIT_TEMPERATURE sentinel."""
        from providers.base import ProviderProfile, OMIT_TEMPERATURE

        msgs = [{"role": "user", "content": "Hi"}]
        kw = transport.build_kwargs(
            model="gpt-4o",
            messages=msgs,
            provider_profile=ProviderProfile(
                name="_t", fixed_temperature=OMIT_TEMPERATURE
            ),
        )
        assert "temperature" not in kw


class TestChatCompletionsKimi:
    """Regression tests for the Kimi/Moonshot quirks migrated into the transport."""

    def test_moonshot_tool_schemas_are_sanitized_by_model_name(self, transport):
        """Aggregator routes (Nous, OpenRouter) hit Moonshot by model name, not base URL."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "q": {"description": "query"},  # missing type
                        },
                    },
                },
            },
        ]
        kw = transport.build_kwargs(
            model="moonshotai/kimi-k2.6",
            messages=[{"role": "user", "content": "Hi"}],
            tools=tools,
            max_tokens_param_fn=lambda n: {"max_tokens": n},
        )
        assert (
            kw["tools"][0]["function"]["parameters"]["properties"]["q"]["type"]
            == "string"
        )

    def test_moonshot_outgoing_schema_carries_required_array(self, transport):
        """Moonshot 400s on object schemas without an explicit `required` array
        (#66835). Assert the wire-level tool schema — what actually leaves the
        transport — carries `required: []` on a zero-required-param tool."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "browser_snapshot",
                    "description": "Snapshot",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]
        kw = transport.build_kwargs(
            model="moonshotai/kimi-k3",
            messages=[{"role": "user", "content": "Hi"}],
            tools=tools,
            max_tokens_param_fn=lambda n: {"max_tokens": n},
        )
        assert kw["tools"][0]["function"]["parameters"]["required"] == []

    def test_non_moonshot_tools_are_not_mutated(self, transport):
        """Other models don't go through the Moonshot sanitizer."""
        original_params = {
            "type": "object",
            "properties": {"q": {"description": "query"}},  # missing type
        }
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": original_params,
                },
            },
        ]
        kw = transport.build_kwargs(
            model="anthropic/claude-sonnet-4.6",
            messages=[{"role": "user", "content": "Hi"}],
            tools=tools,
            max_tokens_param_fn=lambda n: {"max_tokens": n},
        )
        # The parameters dict is passed through untouched (no synthetic type)
        assert "type" not in kw["tools"][0]["function"]["parameters"]["properties"]["q"]


class TestChatCompletionsLmStudioReasoning:
    """LM Studio publishes per-model reasoning ``allowed_options``. When the
    user requests an effort the model can't honor (e.g. ``high`` on a
    toggle-style ``["off","on"]`` model), the lmstudio profile omits
    ``reasoning_effort`` so LM Studio falls back to the model's default —
    silently downgrading "high" to "low" would mislead the user.
    """

    def test_omits_effort_when_high_not_allowed_toggle(self, transport):
        kw = transport.build_kwargs(
            model="gpt-oss",
            messages=[{"role": "user", "content": "Hi"}],
            provider_profile=get_provider_profile("lmstudio"),
            supports_reasoning=True,
            reasoning_config={"effort": "high"},
            lmstudio_reasoning_options=["off", "on"],
        )
        assert "reasoning_effort" not in kw

    def test_passes_through_when_effort_allowed(self, transport):
        kw = transport.build_kwargs(
            model="gpt-oss",
            messages=[{"role": "user", "content": "Hi"}],
            provider_profile=get_provider_profile("lmstudio"),
            supports_reasoning=True,
            reasoning_config={"effort": "high"},
            lmstudio_reasoning_options=["off", "low", "medium", "high"],
        )
        assert kw["reasoning_effort"] == "high"


class TestChatCompletionsValidate:
    def test_none(self, transport):
        assert transport.validate_response(None) is False

    @pytest.mark.parametrize("usage", [None, SimpleNamespace(completion_tokens=0)])
    def test_rejects_known_router_timeout_shim_without_generated_tokens(
        self, transport, usage
    ):
        """#68396: an HTTP-200 router timeout shim with no generated tokens is not a completion."""
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Connect timeout, please try again later.",
                        tool_calls=None,
                    )
                )
            ],
            usage=usage,
        )

        assert transport.validate_response(response) is False

    @pytest.mark.parametrize(
        ("content", "tool_calls", "usage"),
        [
            (
                "Connect timeout, please try again later.",
                None,
                SimpleNamespace(completion_tokens=1),
            ),
            ("Connect timeout, please try again later.", [SimpleNamespace()], None),
        ],
    )
    def test_accepts_non_shim_timeout_text(self, transport, content, tool_calls, usage):
        """Positive controls (#68396): generated tokens, embedded phrase, or tool calls stay valid."""
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content, tool_calls=tool_calls)
                )
            ],
            usage=usage,
        )

        assert transport.validate_response(response) is True

    def test_valid(self, transport):
        r = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))]
        )
        assert transport.validate_response(r) is True


class TestChatCompletionsNormalize:
    def test_text_response(self, transport):
        r = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Hello", tool_calls=None, reasoning_content=None
                    ),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=10, completion_tokens=5, total_tokens=15
            ),
        )
        nr = transport.normalize_response(r)
        assert isinstance(nr, NormalizedResponse)
        assert nr.content == "Hello"
        assert nr.finish_reason == "stop"
        assert nr.tool_calls is None

    def test_tool_call_response(self, transport):
        tc = SimpleNamespace(
            id="call_123",
            function=SimpleNamespace(name="terminal", arguments='{"command": "ls"}'),
        )
        r = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=None, tool_calls=[tc], reasoning_content=None
                    ),
                    finish_reason="tool_calls",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=10, completion_tokens=20, total_tokens=30
            ),
        )
        nr = transport.normalize_response(r)
        assert len(nr.tool_calls) == 1
        assert nr.tool_calls[0].name == "terminal"
        assert nr.tool_calls[0].id == "call_123"

    def test_empty_reasoning_content_preserved(self, transport):
        """DeepSeek can require an explicit empty reasoning_content replay field."""
        r = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=None,
                        tool_calls=None,
                        reasoning=None,
                        reasoning_content="",
                    ),
                    finish_reason="stop",
                )
            ],
            usage=None,
        )
        nr = transport.normalize_response(r)
        assert nr.provider_data == {"reasoning_content": ""}
        assert nr.reasoning_content == ""


class TestChatCompletionsCacheStats:
    def test_no_usage(self, transport):
        r = SimpleNamespace(usage=None)
        assert transport.extract_cache_stats(r) is None

    def test_deepseek_native_top_level_cache_hit_tokens(self, transport):
        """DeepSeek's native API (api.deepseek.com) reports cache hits as
        top-level prompt_cache_hit_tokens, not the OpenAI nested shape —
        the extractor must read it or direct DeepSeek sessions show 0%
        cache hit rate (#61871)."""
        r = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens_details=None,
                prompt_cache_hit_tokens=1500,
                prompt_cache_miss_tokens=500,
            )
        )
        result = transport.extract_cache_stats(r)
        assert result == {"cached_tokens": 1500, "creation_tokens": 0}

    def test_nested_details_win_over_deepseek_top_level(self, transport):
        """When both shapes are present, the OpenAI nested value wins."""
        details = SimpleNamespace(cached_tokens=800, cache_write_tokens=0)
        r = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens_details=details,
                prompt_cache_hit_tokens=1500,
            )
        )
        result = transport.extract_cache_stats(r)
        assert result == {"cached_tokens": 800, "creation_tokens": 0}
