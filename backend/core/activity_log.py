"""In-memory activity log the UI can show and the user can copy.

The desktop app deliberately shows no notifications, so this is the only
place a failure becomes visible. Everything that goes through Python's
logging — feature events, swallowed exceptions, LCU failures, renderer
errors forwarded by the UI — lands in one ring buffer that the Logs tab
reads and the user can paste somewhere for help.
"""
import logging
import logging.handlers
import threading
import time
import traceback
from collections import deque
from pathlib import Path

from core.paths import is_frozen, user_data_dir

#: Access logs would bury everything else: the UI polls twice every 4 seconds.
EXCLUDED_LOGGERS = ("uvicorn.access",)

DEFAULT_CAPACITY = 750

#: Logger used for entries forwarded by the renderer process.
RENDERER_LOGGER = "renderer"


class ActivityLog(logging.Handler):
    """Bounded, thread-safe buffer of recent log records."""

    def __init__(self, capacity=DEFAULT_CAPACITY):
        super().__init__()
        self._entries = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._next_seq = 1

    def emit(self, record):
        if record.name.startswith(EXCLUDED_LOGGERS):
            return
        try:
            entry = self._build_entry(record)
        except Exception:  # never let logging break the caller
            return
        self._append(entry)

    def _append(self, entry):
        """Add an entry, collapsing an immediate repeat into a counter.

        Loops poll every couple of seconds, so a persistent failure would
        otherwise push everything else out of the buffer and make the log
        useless to read or paste.
        """
        with self._lock:
            previous = self._entries[-1] if self._entries else None
            if previous is not None and _same_event(previous, entry):
                previous["count"] = previous.get("count", 1) + 1
                previous["ts"] = entry["ts"]
                return

            entry["seq"] = self._next_seq
            entry["count"] = 1
            self._next_seq += 1
            self._entries.append(entry)

    def _build_entry(self, record):
        detail = None
        if record.exc_info:
            detail = "".join(traceback.format_exception(*record.exc_info)).rstrip()

        return {
            "ts": record.created,
            "level": record.levelname,
            "source": record.name,
            "message": record.getMessage(),
            "detail": detail,
        }

    def entries(self, after=0, limit=DEFAULT_CAPACITY):
        """Entries with seq > `after`, oldest first."""
        with self._lock:
            selected = [e for e in self._entries if e["seq"] > after]
        return selected[-limit:]

    def record(self, level, message, source=RENDERER_LOGGER, detail=None):
        """Add an entry that did not come from a Python logger."""
        self._append(
            {
                "ts": time.time(),
                "level": (level or "INFO").upper(),
                "source": source,
                "message": message,
                "detail": detail,
            }
        )

    def clear(self):
        with self._lock:
            self._entries.clear()


def _same_event(a, b):
    return (
        a["level"] == b["level"]
        and a["source"] == b["source"]
        and a["message"] == b["message"]
        and a["detail"] == b["detail"]
    )


ACTIVITY_LOG = ActivityLog()

#: 2MB x 3 backups is plenty for a local single-user app and keeps a crash
#: report from ever needing a multi-megabyte file attached.
LOG_FILE_MAX_BYTES = 2 * 1024 * 1024
LOG_FILE_BACKUP_COUNT = 3


def _log_file_dir():
    base = user_data_dir() if is_frozen() else Path(__file__).resolve().parent.parent
    return base / "logs"


def _build_file_handler():
    """A RotatingFileHandler so a crash or a hang the in-memory buffer never
    got to show still leaves a trace on disk to diagnose later.
    """
    log_dir = _log_file_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "camargo.log",
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",  # player/summoner names are frequently non-ASCII
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    return handler


#: Chatty at DEBUG and never interesting when diagnosing this app.
NOISY_LOGGERS = ("asyncio", "urllib3", "httpx", "httpcore", "charset_normalizer")

#: Our own packages: everything, down to DEBUG.
APP_LOGGERS = ("features", "core", "api", RENDERER_LOGGER)


def install(level=logging.DEBUG):
    """Route logging through the buffer and a rotating file, once.

    The root stays at INFO so third-party libraries do not bury the entries
    that matter; only this project's loggers go down to DEBUG.
    """
    root = logging.getLogger()
    if ACTIVITY_LOG not in root.handlers:
        root.addHandler(ACTIVITY_LOG)
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        root.addHandler(_build_file_handler())

    root.setLevel(logging.INFO)
    for name in APP_LOGGERS:
        logging.getLogger(name).setLevel(level)
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    # EXCLUDED_LOGGERS only keeps uvicorn.access out of ACTIVITY_LOG's own
    # in-memory view; the file handler has no equivalent filter, so it must
    # be silenced at the source or every poll request would flood the file.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    return ACTIVITY_LOG
