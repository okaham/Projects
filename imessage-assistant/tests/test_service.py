"""Tests for the launchd installer. launchctl doesn't exist on Linux, so it's faked."""

import plistlib
import subprocess

import pytest

import scripts.service as service


@pytest.fixture
def fake_mac(monkeypatch, tmp_path):
    """A fake project folder + home folder, and a launchctl that just records its arguments."""
    project = tmp_path / "Projects" / "imessage-assistant"
    (project / ".venv" / "bin").mkdir(parents=True)
    (project / ".venv" / "bin" / "python").touch()
    (project / ".env").touch()
    home = tmp_path / "home"

    monkeypatch.setattr(service, "PROJECT_DIR", project)
    monkeypatch.setattr(service, "VENV_PYTHON", project / ".venv" / "bin" / "python")
    monkeypatch.setattr(service, "LOG_DIR", project / "logs")
    monkeypatch.setattr(service, "PLIST_PATH", home / "Library" / "LaunchAgents" / "x.plist")
    monkeypatch.setattr(service, "MORNING_PLIST_PATH", home / "Library" / "LaunchAgents" / "m.plist")
    monkeypatch.setattr(service, "_morning_time", lambda: "")  # morning summary off unless a test sets it
    monkeypatch.setattr(service.Path, "home", lambda: home)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[1])  # e.g. "bootout", "bootstrap"
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(service.subprocess, "run", fake_run)
    return {"project": project, "calls": calls}


def test_plist_is_valid_and_keeps_service_alive():
    data = plistlib.loads(plistlib.dumps(service.build_plist()))  # round-trip through real plist XML
    assert data["KeepAlive"] is True and data["RunAtLoad"] is True
    assert data["EnvironmentVariables"]["LOG_TO_CONSOLE"] == "false"
    assert data["ProgramArguments"][1:4] == ["-m", "uvicorn", "app.main:app"]
    assert "127.0.0.1" in data["ProgramArguments"]  # never exposed to the network


def test_install_writes_plist_and_loads_it(fake_mac):
    service.install()
    assert service.PLIST_PATH.exists()
    assert (fake_mac["project"] / "logs").is_dir()
    # server: unload any old copy, then load. Morning summary is off: unload in case it was on.
    assert fake_mac["calls"] == ["bootout", "bootstrap", "bootout"]
    assert not service.MORNING_PLIST_PATH.exists()


def test_install_with_morning_summary(fake_mac, monkeypatch):
    monkeypatch.setattr(service, "_morning_time", lambda: "07:30")
    service.install()
    data = plistlib.loads(service.MORNING_PLIST_PATH.read_bytes())
    assert data["StartCalendarInterval"] == {"Hour": 7, "Minute": 30}
    assert data["ProgramArguments"][1:] == ["-m", "scripts.morning_summary"]
    assert fake_mac["calls"] == ["bootout", "bootstrap", "bootout", "bootstrap"]


def test_install_rejects_bad_morning_time(fake_mac, monkeypatch):
    monkeypatch.setattr(service, "_morning_time", lambda: "7am")
    with pytest.raises(SystemExit, match="07:30"):
        service.install()
    assert fake_mac["calls"] == []  # nothing touched


@pytest.mark.parametrize("value, expected", [("07:30", (7, 30)), ("23:59", (23, 59)), ("0:05", (0, 5))])
def test_parse_time(value, expected):
    assert service.parse_time(value) == expected


@pytest.mark.parametrize("value", ["7am", "24:00", "07:60", "0730", ""])
def test_parse_time_rejects(value):
    with pytest.raises(ValueError):
        service.parse_time(value)


def test_install_refuses_without_env(fake_mac):
    (fake_mac["project"] / ".env").unlink()
    with pytest.raises(SystemExit, match=".env"):
        service.install()
    assert fake_mac["calls"] == []


def test_install_refuses_protected_folder(fake_mac, monkeypatch, tmp_path):
    home = tmp_path / "home"
    project = home / "Documents" / "imessage-assistant"
    monkeypatch.setattr(service, "PROJECT_DIR", project)
    with pytest.raises(SystemExit, match="Desktop, Documents and Downloads"):
        service.install()


def test_uninstall_removes_both_plists(fake_mac, monkeypatch):
    monkeypatch.setattr(service, "_morning_time", lambda: "07:30")
    service.install()
    service.uninstall()
    assert not service.PLIST_PATH.exists()
    assert not service.MORNING_PLIST_PATH.exists()
