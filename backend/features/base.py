"""Common contract every automation/customization module implements."""
from abc import ABC, abstractmethod


class Feature(ABC):
    #: unique slug used in the API/registry, e.g. "auto_accept"
    key: str = ""
    #: human readable title for the UI
    title: str = ""
    #: grouping shown in the UI, e.g. "Automation", "Customization"
    category: str = ""

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
