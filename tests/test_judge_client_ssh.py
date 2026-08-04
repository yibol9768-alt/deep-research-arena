from __future__ import annotations

import json
from types import SimpleNamespace

from src.verifiers.judge_client import call_judge


def test_ssh_openai_sends_json_over_stdin_without_port_forwarding(
    monkeypatch,
):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "choices": [
                        {"message": {"content": '{"verdicts":[]}'}}
                    ]
                }
            ),
            stderr="",
        )

    monkeypatch.setenv("JUDGE_PROVIDER", "ssh_openai")
    monkeypatch.setenv("JUDGE_SSH_HOST", "my5090")
    monkeypatch.setenv("JUDGE_SSH_WSL_DISTRO", "Ubuntu")
    monkeypatch.setenv(
        "JUDGE_SSH_BASE_URL",
        "http://127.0.0.1:8000/v1",
    )
    monkeypatch.setattr("subprocess.run", fake_run)

    text, error = call_judge(
        "system prompt",
        "user payload",
        model="qwen3-8b",
        max_tokens=123,
        temperature=0.0,
    )
    assert error is None
    assert text == '{"verdicts":[]}'
    command = captured["command"]
    assert "-L" not in command
    assert command[-1] == (
        "http://127.0.0.1:8000/v1/chat/completions"
    )
    assert "system prompt" not in command
    assert "user payload" not in command
    request = json.loads(captured["kwargs"]["input"])
    assert request["model"] == "qwen3-8b"
    assert request["chat_template_kwargs"] == {"enable_thinking": False}
    assert request["messages"][1]["content"] == "user payload"


def test_ssh_openai_retries_transient_ssh_failure(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            return SimpleNamespace(
                returncode=255,
                stdout="",
                stderr="connection reset",
            )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"choices": [{"message": {"content": "ok"}}]}
            ),
            stderr="",
        )

    monkeypatch.setenv("JUDGE_PROVIDER", "ssh_openai")
    monkeypatch.setenv("JUDGE_SSH_HOST", "my5090")
    monkeypatch.setenv("JUDGE_SSH_RETRIES", "2")
    monkeypatch.setattr("subprocess.run", fake_run)
    text, error = call_judge(
        "s",
        "u",
        model="qwen3-8b",
        max_tokens=10,
        temperature=0.0,
    )
    assert (text, error) == ("ok", None)
    assert len(calls) == 2
