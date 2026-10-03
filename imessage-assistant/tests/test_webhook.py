"""Tests for the webhook filters. Claude and BlueBubbles are replaced with fakes - no network calls."""

import dataclasses

import pytest
from fastapi.testclient import TestClient

import app.main as main
import app.memory as memory
from app.config import normalize_address


@pytest.fixture
def fakes(monkeypatch):
    """Swap the real Claude/BlueBubbles calls for fakes that record what they were called with."""
    calls = {"claude": [], "history": [], "sent": []}

    def fake_get_reply(text, history=None):
        calls["claude"].append(text)
        calls["history"].append(history)
        return f"echo: {text}"

    def fake_send_text(chat_guid, text):
        calls["sent"].append((chat_guid, text))

    monkeypatch.setattr(main, "get_reply", fake_get_reply)
    monkeypatch.setattr(main, "send_text", fake_send_text)
    main._seen_guids.clear()
    return calls


client = TestClient(main.app)


def make_payload(text="hi", sender="+15551234567", is_from_me=False, guid="msg-1",
                 chat_guid=None, event_type="new-message", reaction=None):
    return {
        "type": event_type,
        "data": {
            "guid": guid,
            "text": text,
            "isFromMe": is_from_me,
            "associatedMessageGuid": reaction,
            "handle": {"address": sender},
            "chats": [{"guid": chat_guid or f"iMessage;-;{sender}"}],
        },
    }


def post(payload, secret="s3cret"):
    return client.post(f"/webhook?secret={secret}", json=payload)


def test_allowed_sender_gets_reply(fakes):
    r = post(make_payload(text="hello"))
    assert r.status_code == 200
    assert fakes["claude"] == ["hello"]
    assert fakes["sent"] == [("iMessage;-;+15551234567", "echo: hello")]


def test_allowed_email_sender_gets_reply(fakes):
    post(make_payload(sender="Me@iCloud.com"))
    assert len(fakes["sent"]) == 1


def test_unknown_sender_ignored(fakes):
    post(make_payload(sender="+15559999999"))
    assert fakes["claude"] == [] and fakes["sent"] == []


def test_own_messages_ignored(fakes):
    post(make_payload(is_from_me=True))
    assert fakes["sent"] == []


def test_group_chat_ignored(fakes):
    post(make_payload(chat_guid="iMessage;+;chat123456"))
    assert fakes["sent"] == []


def test_reaction_ignored(fakes):
    post(make_payload(text='Loved "hi"', reaction="p:0/abc"))
    assert fakes["sent"] == []


def test_other_event_types_ignored(fakes):
    post(make_payload(event_type="updated-message"))
    assert fakes["sent"] == []


def test_duplicate_delivery_answered_once(fakes):
    post(make_payload(guid="same"))
    post(make_payload(guid="same"))
    assert len(fakes["sent"]) == 1


def test_wrong_secret_rejected(fakes):
    r = post(make_payload(), secret="wrong")
    assert r.status_code == 403
    assert fakes["sent"] == []


def test_claude_error_is_reported_not_swallowed(fakes, monkeypatch, caplog):
    def broken(text, history=None):
        raise RuntimeError("API down")

    monkeypatch.setattr(main, "get_reply", broken)
    post(make_payload())
    assert "Failed to handle message" in caplog.text
    assert len(fakes["sent"]) == 1 and "Sorry" in fakes["sent"][0][1]


# --- Memory (Phase 2) ---

@pytest.fixture
def memory_on(monkeypatch, tmp_path):
    """Turn memory on and point it at a throwaway database in a temp folder."""
    test_settings = dataclasses.replace(
        main.settings, memory_enabled=True, history_limit=20, db_path=str(tmp_path / "test.db")
    )
    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(memory, "settings", test_settings)
    memory.init_db()


def test_memory_off_sends_no_history(fakes):
    post(make_payload(text="first", guid="a"))
    post(make_payload(text="second", guid="b"))
    assert fakes["history"] == [[], []]


def test_memory_on_second_text_sees_first(fakes, memory_on):
    post(make_payload(text="my name is Kevin", guid="a"))
    post(make_payload(text="what's my name?", guid="b"))
    assert fakes["history"][1] == [
        {"role": "user", "content": "my name is Kevin"},
        {"role": "assistant", "content": "echo: my name is Kevin"},
    ]


def test_memory_not_saved_when_claude_fails(fakes, memory_on, monkeypatch):
    def broken(text, history=None):
        raise RuntimeError("API down")

    monkeypatch.setattr(main, "get_reply", broken)
    post(make_payload(text="lost", guid="a"))
    assert memory.get_recent("iMessage;-;+15551234567", 20) == []


def test_memory_save_failure_does_not_send_apology(fakes, memory_on, monkeypatch, caplog):
    def broken_save(*args):
        raise OSError("disk full")

    monkeypatch.setattr(memory, "save_exchange", broken_save)
    post(make_payload(text="hi"))
    assert fakes["sent"] == [("iMessage;-;+15551234567", "echo: hi")]
    assert "saving message" in caplog.text


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+1 (555) 123-4567", "15551234567"),
        ("555-123-4567", "15551234567"),
        ("+15551234567", "15551234567"),
        (" Me@iCloud.com ", "me@icloud.com"),
    ],
)
def test_normalize_address(raw, expected):
    assert normalize_address(raw) == expected
