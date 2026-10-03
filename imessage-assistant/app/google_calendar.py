"""Read-only access to your primary Google Calendar."""

from datetime import date, datetime, time, timedelta

from googleapiclient.discovery import build

from app.google_auth import get_credentials

MAX_DAYS = 31


def _service():
    # cache_discovery=False avoids a harmless but noisy warning from the Google library.
    return build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)


def list_events(start_date: str, days: int) -> list[dict]:
    """Events from midnight on start_date (Mac's local time zone) through `days` days later.

    Raises ValueError for bad input - the caller passes that message back to Claude.
    """
    first_day = date.fromisoformat(start_date)  # raises ValueError if not YYYY-MM-DD
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_DAYS}, got {days}")

    # datetime.combine(...) makes a "naive" local midnight; .astimezone() attaches the Mac's
    # time zone offset *for that date*, so daylight-saving changes are handled correctly.
    start = datetime.combine(first_day, time.min).astimezone()
    end = datetime.combine(first_day + timedelta(days=days), time.min).astimezone()

    result = (
        _service()
        .events()
        .list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,  # expand repeating events into individual occurrences
            orderBy="startTime",
            maxResults=250,
        )
        .execute()
    )
    return [_simplify(e) for e in result.get("items", [])]


def _simplify(event: dict) -> dict:
    """Keep only what Claude needs. Timed events have start.dateTime; all-day events have start.date."""
    start, end = event.get("start", {}), event.get("end", {})
    return {
        "title": event.get("summary", "(no title)"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start,
        "location": event.get("location"),
    }
