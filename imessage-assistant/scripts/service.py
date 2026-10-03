"""Run the assistant as a macOS background service (launchd) that starts at login and restarts if it crashes.

    python -m scripts.service install     # create the service and start it (+ morning summary if set in .env)
    python -m scripts.service status      # is it running? does /health answer?
    python -m scripts.service restart     # after changing code or .env
    python -m scripts.service uninstall   # stop it and remove it

What launchd is: macOS's built-in process manager (like systemd on Linux, or
Windows Services). We give it a small XML file (a "plist") that says which command
to run and to keep it alive. It lives in ~/Library/LaunchAgents/, so it runs as
you, while you're logged in. It has to be a per-user "agent" and not a system-wide
"daemon", because BlueBubbles and Messages also run inside your login session.
"""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "local.imessage-assistant"  # unique name launchd uses for this service
MORNING_LABEL = "local.imessage-assistant.morning"
PORT = 8000

PROJECT_DIR = Path(__file__).resolve().parent.parent  # the imessage-assistant folder
VENV_PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"
LOG_DIR = PROJECT_DIR / "logs"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
MORNING_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{MORNING_LABEL}.plist"


def build_plist() -> dict:
    """The service definition. plistlib turns this dict into launchd's XML format."""
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(VENV_PYTHON), "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(PORT),
            "--no-access-log",  # our own log already records every webhook
        ],
        # Run from the project folder so relative paths in .env (logs/, data/) resolve correctly.
        "WorkingDirectory": str(PROJECT_DIR),
        "RunAtLoad": True,       # start as soon as it's installed, and at every login
        "KeepAlive": True,       # if the process exits for any reason, start it again
        "ThrottleInterval": 10,  # ...but wait at least 10 seconds between restarts
        "EnvironmentVariables": {
            "LOG_TO_CONSOLE": "false",  # everything goes to logs/assistant.log instead
            "PYTHONUNBUFFERED": "1",    # write crash output immediately, not in chunks
        },
        # Only catches output from before our logging starts (e.g. a missing .env
        # setting crashes at startup). Normal logs are in logs/assistant.log.
        "StandardOutPath": str(LOG_DIR / "launchd.out.log"),
        "StandardErrorPath": str(LOG_DIR / "launchd.err.log"),
    }


def parse_time(value: str) -> tuple[int, int]:
    """ "07:30" -> (7, 30). Raises ValueError for anything else."""
    hour_text, minute_text = value.split(":")
    hour, minute = int(hour_text), int(minute_text)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(value)
    return hour, minute


def build_morning_plist(hour: int, minute: int) -> dict:
    """A second job that runs scripts.morning_summary once a day and then exits."""
    return {
        "Label": MORNING_LABEL,
        "ProgramArguments": [str(VENV_PYTHON), "-m", "scripts.morning_summary"],
        "WorkingDirectory": str(PROJECT_DIR),
        # Runs daily at this local time. If the Mac was asleep then, launchd runs it on wake.
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "EnvironmentVariables": {"LOG_TO_CONSOLE": "false", "PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(LOG_DIR / "morning.out.log"),
        "StandardErrorPath": str(LOG_DIR / "morning.err.log"),
    }


def _load(label: str, plist_path: Path, plist: dict) -> None:
    """Write a plist and (re)load it into launchd."""
    # If an older version is loaded, unload it first. Fails harmlessly if it isn't loaded.
    _launchctl("bootout", f"{_domain()}/{label}", check=False)
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)
    print(f"Wrote {plist_path}")
    result = _launchctl("bootstrap", _domain(), str(plist_path), check=False)
    if result.returncode != 0:
        sys.exit(f"launchctl bootstrap failed for {label}:\n{result.stderr}")


def _unload(label: str, plist_path: Path) -> None:
    _launchctl("bootout", f"{_domain()}/{label}", check=False)
    if plist_path.exists():
        plist_path.unlink()


def _morning_time() -> str:
    # Imported here (not at the top) so the tests and `uninstall` don't need a complete .env.
    from app.config import settings
    return settings.morning_summary_time


def _launchctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    # "gui/<your user id>" is launchd's name for your login session.
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=check)


def _domain() -> str:
    return f"gui/{os.getuid()}"


def install() -> None:
    protected = [Path.home() / name for name in ("Desktop", "Documents", "Downloads")]
    if any(p in PROJECT_DIR.parents for p in protected):
        sys.exit(
            f"The project is in {PROJECT_DIR}.\n"
            "macOS blocks background services from reading Desktop, Documents and Downloads.\n"
            "Move it somewhere like ~/Projects and run this again."
        )
    if not VENV_PYTHON.exists():
        sys.exit(f"Not found: {VENV_PYTHON}\nCreate the virtual environment first (README, Part 1).")
    if not (PROJECT_DIR / ".env").exists():
        sys.exit(f"Not found: {PROJECT_DIR / '.env'}\nCreate it first (README, Part 1).")

    morning = _morning_time()
    if morning:
        try:
            hour, minute = parse_time(morning)
        except ValueError:
            sys.exit(f"MORNING_SUMMARY_TIME must look like 07:30, got {morning!r}")

    LOG_DIR.mkdir(exist_ok=True)  # launchd won't create this folder itself
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    _load(LABEL, PLIST_PATH, build_plist())
    print("Service installed and started. Check it with:  python -m scripts.service status")

    if morning:
        _load(MORNING_LABEL, MORNING_PLIST_PATH, build_morning_plist(hour, minute))
        print(f"Morning summary scheduled daily at {hour:02d}:{minute:02d}.")
    else:
        _unload(MORNING_LABEL, MORNING_PLIST_PATH)  # in case it was on before
        print("Morning summary is off (MORNING_SUMMARY_TIME is empty).")


def uninstall() -> None:
    _unload(LABEL, PLIST_PATH)
    _unload(MORNING_LABEL, MORNING_PLIST_PATH)
    print("Service (and morning summary, if any) stopped and removed.")


def restart() -> None:
    # kickstart -k = kill the running process and start a fresh one (re-reads code and .env).
    result = _launchctl("kickstart", "-k", f"{_domain()}/{LABEL}", check=False)
    if result.returncode != 0:
        sys.exit(f"Restart failed (is it installed?):\n{result.stderr}")
    print("Restarted.")


def status() -> None:
    result = _launchctl("print", f"{_domain()}/{LABEL}", check=False)
    if result.returncode != 0:
        print("Service is NOT installed.")
        return

    # `launchctl print` outputs a lot; show only the useful lines.
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith(("state =", "pid =", "runs =", "last exit code =")):
            print(" ", line)

    morning = _launchctl("print", f"{_domain()}/{MORNING_LABEL}", check=False)
    print("  morning summary:", "scheduled" if morning.returncode == 0 else "off")

    import httpx  # imported here so the other commands work even outside the venv
    try:
        r = httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=5)
        print(f"  /health -> {r.status_code} {r.text}")
    except httpx.HTTPError as e:
        print(f"  /health -> not answering ({e}). Look at logs/launchd.err.log and logs/assistant.log")


COMMANDS = {"install": install, "uninstall": uninstall, "restart": restart, "status": status}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"Usage: python -m scripts.service [{'|'.join(COMMANDS)}]")
    if sys.platform != "darwin":
        sys.exit("This only works on macOS.")
    COMMANDS[sys.argv[1]]()
