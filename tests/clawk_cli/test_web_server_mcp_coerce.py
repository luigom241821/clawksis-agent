"""``_mcp_server_summary`` tolerates ``env`` / ``args`` stored as strings in hand-edited config.yaml
(one malformed entry must not 500 ``GET /api/mcp/servers``)."""

from clawk_cli.web_server_mcp import _coerce_sequence, _mcp_server_summary


def test_summary_parses_json_string_env_and_args():
    summary = _mcp_server_summary(
        "srv", {"command": "npx", "args": '["-y", "pkg"]', "env": '{"API_KEY": "sk-abcdef123456"}'}
    )

    assert summary["args"] == ["-y", "pkg"]
    assert set(summary["env"]) == {"API_KEY"}
    assert summary["env"]["API_KEY"] != "sk-abcdef123456"  # still redacted


def test_summary_survives_unparseable_strings():
    summary = _mcp_server_summary("srv", {"command": "srv-bin", "args": "--stdio", "env": "not json"})

    assert summary["args"] == ["--stdio"]  # one arg, not a char sequence
    assert summary["env"] == {}


def test_coerce_sequence_keeps_lists_and_empties():
    assert _coerce_sequence(["a"]) == ["a"]
    assert _coerce_sequence(None) == []
    assert _coerce_sequence("") == []
