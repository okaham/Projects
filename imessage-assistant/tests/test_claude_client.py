"""Tests for the tool loop in claude_client, with a fake Claude that returns scripted responses."""

import dataclasses
from types import SimpleNamespace

import pytest

import app.claude_client as cc
import app.tools as tools


def text_response(text):
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


def tool_response(tool_id="tu_1", name="list_calendar_events", tool_input=None):
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", id=tool_id, name=name,
                                 input=tool_input or {"start_date": "2026-10-03", "days": 1})],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


class FakeClaude:
    """Stands in for anthropic.Anthropic(). Returns the given responses in order and records requests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **request):
        # Copy the messages list: the real code keeps appending to it after this call.
        self.requests.append({**request, "messages": list(request["messages"])})
        return self.responses.pop(0)


@pytest.fixture
def calendar_on(monkeypatch):
    on = dataclasses.replace(tools.settings, google_calendar_enabled=True)
    monkeypatch.setattr(tools, "settings", on)


def test_plain_reply_sends_no_tools(monkeypatch):
    fake = FakeClaude([text_response("hi there")])
    monkeypatch.setattr(cc, "client", fake)
    assert cc.get_reply("hello") == "hi there"
    assert "tools" not in fake.requests[0]
    assert "Current local date and time" in fake.requests[0]["system"]


def test_tool_call_runs_tool_and_sends_result_back(monkeypatch, calendar_on):
    fake = FakeClaude([tool_response(), text_response("You have dentist at 3pm.")])
    monkeypatch.setattr(cc, "client", fake)
    monkeypatch.setattr(cc, "run_tool", lambda name, inp: ('[{"title": "Dentist"}]', False))

    assert cc.get_reply("what's on today?") == "You have dentist at 3pm."
    assert fake.requests[0]["tools"][0]["name"] == "list_calendar_events"

    second = fake.requests[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    result = second[2]["content"][0]
    assert result == {"type": "tool_result", "tool_use_id": "tu_1",
                      "content": '[{"title": "Dentist"}]', "is_error": False}


def test_tool_loop_stops_after_max_rounds(monkeypatch, calendar_on):
    fake = FakeClaude([tool_response(tool_id=f"tu_{i}") for i in range(cc.MAX_TOOL_ROUNDS + 1)])
    monkeypatch.setattr(cc, "client", fake)
    monkeypatch.setattr(cc, "run_tool", lambda name, inp: ("[]", False))
    assert "too many steps" in cc.get_reply("loop forever")
    assert len(fake.requests) == cc.MAX_TOOL_ROUNDS + 1


def test_refusal(monkeypatch):
    refusal = SimpleNamespace(stop_reason="refusal", content=[],
                              usage=SimpleNamespace(input_tokens=1, output_tokens=0))
    monkeypatch.setattr(cc, "client", FakeClaude([refusal]))
    assert "can't help" in cc.get_reply("x")


def test_history_is_not_modified(monkeypatch, calendar_on):
    """The tool loop appends to its own messages list, never to the caller's history."""
    history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    monkeypatch.setattr(cc, "client", FakeClaude([tool_response(), text_response("ok")]))
    monkeypatch.setattr(cc, "run_tool", lambda name, inp: ("[]", False))
    cc.get_reply("c", history)
    assert len(history) == 2
