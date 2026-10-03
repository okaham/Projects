"""Run the assistant as a macOS background service (launchd) that starts at login and restarts if it crashes.

    python -m scripts.service install     # create the service and start it
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
PORT = 8000

PROJECT_DIR = Path(__file__).resolve().parent.parent  # the imessage-assistant folder
VENV_PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"
LOG_DIR = PROJECT_DIR / "logs"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


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

    LOG_DIR.mkdir(exist_ok=True)  # launchd won't create this folder itself
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    # If an older version is loaded, unload it first. Fails harmlessly if it isn't loaded.
    _launchctl("bootout", f"{_domain()}/{LABEL}", check=False)

    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(build_plist(), f)
    print(f"Wrote {PLIST_PATH}")

    result = _launchctl("bootstrap", _domain(), str(PLIST_PATH), check=False)
    if result.returncode != 0:
        sys.exit(f"launchctl bootstrap failed:\n{result.stderr}")
    print("Service installed and started. Check it with:  python -m scripts.service status")


def uninstall() -> None:
    _launchctl("bootout", f"{_domain()}/{LABEL}", check=False)
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
    print("Service stopped and removed.")


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
