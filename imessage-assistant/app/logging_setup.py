"""Send log messages to a rotating log file, and to the terminal when running by hand."""

import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(log_file: str, to_console: bool = True) -> None:
    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    # Keeps up to 5 files of 1 MB each (assistant.log, assistant.log.1, ...) so the disk never fills up.
    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5)
    file_handler.setFormatter(fmt)

    handlers: list[logging.Handler] = [file_handler]
    # Under launchd there is no terminal: console output goes to a file that never rotates,
    # so the launchd service turns this off (LOG_TO_CONSOLE=false) to avoid logging everything twice.
    if to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(fmt)
        handlers.append(console_handler)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = handlers

    # uvicorn's own logger doesn't pass messages up to the root logger, so give it the file
    # handler too - otherwise server-level crashes would only show in the terminal.
    logging.getLogger("uvicorn").addHandler(file_handler)

    # httpx logs every HTTP request at INFO, and the URL contains the BlueBubbles
    # password as a query parameter. Raise its level so the password never hits the log file.
    logging.getLogger("httpx").setLevel(logging.WARNING)
