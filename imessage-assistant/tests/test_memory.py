"""Tests for the SQLite memory module, using a throwaway database per test."""

import dataclasses

import pytest

import app.memory as memory

CHAT = "iMessage;-;+15551234567"


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    test_settings = dataclasses.replace(memory.settings, db_path=str(tmp_path / "sub" / "test.db"))
    monkeypatch.setattr(memory, "settings", test_settings)
    memory.init_db()  # also checks that the "sub" folder gets created


def test_empty_chat_has_no_history():
    assert memory.get_recent(CHAT, 20) == []


def test_history_is_oldest_first():
    memory.save_exchange(CHAT, "q1", "a1", "g1")
    memory.save_exchange(CHAT, "q2", "a2", "g2")
    assert memory.get_recent(CHAT, 20) == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]


def test_limit_keeps_newest():
    for i in range(15):
        memory.save_exchange(CHAT, f"q{i}", f"a{i}", f"g{i}")
    history = memory.get_recent(CHAT, 4)
    assert [m["content"] for m in history] == ["q13", "a13", "q14", "a14"]


def test_odd_limit_never_starts_with_assistant():
    for i in range(3):
        memory.save_exchange(CHAT, f"q{i}", f"a{i}", f"g{i}")
    history = memory.get_recent(CHAT, 3)  # newest 3 = a1, q2, a2 -> a1 dropped
    assert [m["content"] for m in history] == ["q2", "a2"]


def test_chats_are_kept_separate():
    memory.save_exchange(CHAT, "mine", "reply", "g1")
    memory.save_exchange("iMessage;-;other@icloud.com", "theirs", "reply", "g2")
    assert [m["content"] for m in memory.get_recent(CHAT, 20)] == ["mine", "reply"]


def test_init_db_is_safe_to_run_twice():
    memory.save_exchange(CHAT, "q", "a", "g")
    memory.init_db()
    assert len(memory.get_recent(CHAT, 20)) == 2
