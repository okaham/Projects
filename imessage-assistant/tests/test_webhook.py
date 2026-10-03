"""Tests for the webhook filters. Claude and BlueBubbles are replaced with fakes - no network calls."""

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.config import normalize_address


@pytest.fixture
def fakes(monkeypatch):
    """Swap the real Claude/BlueBubbles calls for fakes that record what they were called with."""
    calls = {"claude": [], "sent": []}

    def fake_get_reply(text):
        calls["claude"].append(text)
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
    def broken(text):
        raise RuntimeError("API down")

    monkeypatch.setattr(main, "get_reply", broken)
    post(make_payload())
    assert "Failed to handle message" in caplog.text
    assert len(fakes["sent"]) == 1 and "Sorry" in fakes["sent"][0][1]


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
