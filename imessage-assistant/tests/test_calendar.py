"""Tests for the Calendar tool and Google sign-in, with Google's API faked."""

import dataclasses
import json
from datetime import datetime

import pytest

import app.google_auth as google_auth
import app.google_calendar as gcal
import app.tools as tools


class FakeEvents:
    def __init__(self, items):
        self.items = items
        self.list_kwargs = None

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return self

    def execute(self):
        return {"items": self.items}


@pytest.fixture
def fake_google(monkeypatch):
    events = FakeEvents([
        {"summary": "Dentist", "location": "Main St",
         "start": {"dateTime": "2026-10-03T15:00:00-07:00"}, "end": {"dateTime": "2026-10-03T16:00:00-07:00"}},
        {"summary": "Mom's birthday", "start": {"date": "2026-10-03"}, "end": {"date": "2026-10-04"}},
        {"start": {"dateTime": "2026-10-03T18:00:00-07:00"}, "end": {"dateTime": "2026-10-03T19:00:00-07:00"}},
    ])
    service = type("Service", (), {"events": lambda self: events})()
    monkeypatch.setattr(gcal, "_service", lambda: service)
    return events


def test_events_are_simplified(fake_google):
    events = gcal.list_events("2026-10-03", 1)
    assert events[0] == {"title": "Dentist", "start": "2026-10-03T15:00:00-07:00",
                         "end": "2026-10-03T16:00:00-07:00", "all_day": False, "location": "Main St"}
    assert events[1]["all_day"] is True
    assert events[2]["title"] == "(no title)"


def test_time_window_is_local_midnight_to_midnight(fake_google):
    gcal.list_events("2026-10-03", 2)
    start = datetime.fromisoformat(fake_google.list_kwargs["timeMin"])
    end = datetime.fromisoformat(fake_google.list_kwargs["timeMax"])
    assert (start.year, start.month, start.day, start.hour) == (2026, 10, 3, 0)
    assert (end.month, end.day, end.hour) == (10, 5, 0)
    assert start.tzinfo is not None  # has a time zone offset, as Google requires
    assert fake_google.list_kwargs["singleEvents"] is True


@pytest.mark.parametrize("start_date, days", [("tomorrow", 1), ("2026-10-03", 0), ("2026-10-03", 32)])
def test_bad_input_rejected(fake_google, start_date, days):
    with pytest.raises(ValueError):
        gcal.list_events(start_date, days)


# --- run_tool: errors become text for Claude, never exceptions ---

@pytest.fixture
def calendar_on(monkeypatch):
    monkeypatch.setattr(tools, "settings", dataclasses.replace(tools.settings, google_calendar_enabled=True))


def test_run_tool_returns_json(fake_google, calendar_on):
    text, is_error = tools.run_tool("list_calendar_events", {"start_date": "2026-10-03", "days": 1})
    assert not is_error
    assert json.loads(text)[0]["title"] == "Dentist"


def test_run_tool_bad_input_is_error_text(fake_google, calendar_on):
    text, is_error = tools.run_tool("list_calendar_events", {"start_date": "nope", "days": 1})
    assert is_error and "nope" in text


def test_run_tool_disabled(fake_google):
    text, is_error = tools.run_tool("list_calendar_events", {"start_date": "2026-10-03", "days": 1})
    assert is_error and "disabled" in text


def test_enabled_tools_follows_setting(calendar_on):
    assert [t["name"] for t in tools.enabled_tools()] == ["list_calendar_events"]


# --- Google sign-in ---

def test_missing_token_asks_for_login(monkeypatch, tmp_path, calendar_on):
    monkeypatch.setattr(google_auth, "settings",
                        dataclasses.replace(google_auth.settings, google_token_file=str(tmp_path / "none.json")))
    text, is_error = tools.run_tool("list_calendar_events", {"start_date": "2026-10-03", "days": 1})
    assert is_error and "scripts.google_login" in text


def test_expired_refresh_token_asks_for_login(monkeypatch, tmp_path):
    from google.auth.exceptions import RefreshError

    token = tmp_path / "token.json"
    token.write_text(json.dumps({"token": "old", "refresh_token": "r", "client_id": "c",
                                 "client_secret": "s", "expiry": "2020-01-01T00:00:00Z"}))
    monkeypatch.setattr(google_auth, "settings",
                        dataclasses.replace(google_auth.settings, google_token_file=str(token)))

    def refresh_fails(self, request):
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    monkeypatch.setattr(google_auth.Credentials, "refresh", refresh_fails)
    with pytest.raises(google_auth.GoogleLoginNeeded):
        google_auth.get_credentials()
