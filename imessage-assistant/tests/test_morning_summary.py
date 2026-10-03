"""Tests for the scheduled morning summary, with Claude and BlueBubbles faked."""

import dataclasses

import pytest

import app.memory as memory
import scripts.morning_summary as morning
from app.bluebubbles import chat_guid_for
from app.config import settings


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    calls = {"prompts": [], "sent": []}
    monkeypatch.setattr(morning, "get_reply", lambda prompt: calls["prompts"].append(prompt) or "3pm dentist")
    monkeypatch.setattr(morning, "send_text", lambda guid, text: calls["sent"].append((guid, text)))
    on = dataclasses.replace(settings, google_calendar_enabled=True, memory_enabled=True,
                             db_path=str(tmp_path / "m.db"))
    monkeypatch.setattr(morning, "settings", on)
    monkeypatch.setattr(memory, "settings", on)
    return calls


def test_sends_summary_to_owner_and_saves_it(fakes):
    assert morning.main() == 0
    # conftest's ALLOWED_SENDERS starts with "+1 (555) 123-4567"
    assert fakes["sent"] == [("iMessage;-;+15551234567", "3pm dentist")]
    history = memory.get_recent("iMessage;-;+15551234567", 20)
    assert history[1] == {"role": "assistant", "content": "3pm dentist"}


def test_skips_when_calendar_off(fakes, monkeypatch):
    monkeypatch.setattr(morning, "settings", dataclasses.replace(morning.settings, google_calendar_enabled=False))
    assert morning.main() == 1
    assert fakes["sent"] == []


def test_failure_returns_error_code(fakes, monkeypatch, caplog):
    def broken(prompt):
        raise RuntimeError("API down")

    monkeypatch.setattr(morning, "get_reply", broken)
    assert morning.main() == 1
    assert "Morning summary failed" in caplog.text


def test_owner_is_first_allowed_sender():
    assert settings.owner_address == "15551234567"


@pytest.mark.parametrize("address, guid", [
    ("15551234567", "iMessage;-;+15551234567"),
    ("me@icloud.com", "iMessage;-;me@icloud.com"),
])
def test_chat_guid_for(address, guid):
    assert chat_guid_for(address) == guid
