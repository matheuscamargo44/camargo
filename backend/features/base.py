"""Common contract every automation/customization module implements."""
import logging
import threading
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Feature(ABC):
    #: unique slug used in the API/registry, e.g. "auto_accept"
    key: str = ""
    #: human readable title for the UI
    title: str = ""
    #: grouping shown in the UI, e.g. "Automation", "Customization"
    category: str = ""
    #: which shared client the registry injects ("league" -> LCUClient,
    #: "valorant" -> ValorantClient) and which connection gates its actions.
    game: str = "league"

    def __init__(self, lcu_client, config, on_event=None):
        self.lcu = lcu_client
        self.config = config
        self.on_event = on_event or (lambda _level, _message: None)

    @abstractmethod
    def get_status(self) -> dict:
        """Return a JSON-serializable snapshot of this feature's current state."""

    def start(self):
        """Optional: begin any background monitoring loop for this feature."""

    def stop(self):
        """Optional: stop any background monitoring loop for this feature."""


class ThreadedFeature(Feature):
    """Feature that polls the client in the background.

    Subclasses only implement `_loop()`; starting, stopping and joining the
    thread live here. Sleeping inside the loop must go through `self._sleep()`
    so shutdown is immediate instead of waiting out the current interval.
    """

    #: how long stop() waits for the loop to notice the stop event
    JOIN_TIMEOUT_SECONDS = 3.0

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self._stop_event = threading.Event()
        self._thread = None

    @abstractmethod
    def _loop(self):
        """Body of the background thread. Must exit when `_stop_event` is set."""

    def _sleep(self, seconds) -> bool:
        """Sleep, waking early on shutdown. Returns True if we should stop."""
        return self._stop_event.wait(seconds)

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"camargo-{self.key}", daemon=True
        )
        self._thread.start()

    def _run(self):
        try:
            self._loop()
        except Exception:
            # A crashed loop used to die silently; at least leave a trace.
            logger.exception("Background loop for '%s' crashed", self.key)

    def stop(self):
        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=self.JOIN_TIMEOUT_SECONDS)
