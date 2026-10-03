"""Send log messages to both the terminal and a rotating log file."""

import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(log_file: str) -> None:
    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    # Keeps up to 5 files of 1 MB each (assistant.log, assistant.log.1, ...) so the disk never fills up.
    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [file_handler, console_handler]

    # uvicorn's own logger doesn't pass messages up to the root logger, so give it the file
    # handler too - otherwise server-level crashes would only show in the terminal.
    logging.getLogger("uvicorn").addHandler(file_handler)

    # httpx logs every HTTP request at INFO, and the URL contains the BlueBubbles
    # password as a query parameter. Raise its level so the password never hits the log file.
    logging.getLogger("httpx").setLevel(logging.WARNING)
