"""Registers the available features. Adding a new module means adding it here
and nothing else needs to change in the API or the client.
"""
from core.config import load_config
from core.lcu_client import LCUClient
from features.auto_accept import AutoAccept
from features.customization import Background, Badges, ClientIcon, ProfileIcon, RiotId, StatusMessage
from features.dodge import Dodge
from features.instalock_autoban import InstalockAutoban
from features.ragequeue import RageQueue
from features.reveal import Reveal
from features.social import ChatToggle, RemoveFriends, RestartUX

FEATURE_CLASSES = [
    AutoAccept,
    InstalockAutoban,
    Dodge,
    RageQueue,
    Reveal,
    ProfileIcon,
    ClientIcon,
    Background,
    Badges,
    RiotId,
    StatusMessage,
    RemoveFriends,
    RestartUX,
    ChatToggle,
]


class FeatureRegistry:
    def __init__(self, on_event=None):
        self.lcu = LCUClient()
        self.config = load_config()
        self.on_event = on_event or (lambda _level, _message: None)
        self.features = {
            cls.key: cls(self.lcu, self.config, self.on_event) for cls in FEATURE_CLASSES
        }

    def get(self, key):
        feature = self.features.get(key)
        if feature is None:
            raise KeyError(f"Unknown feature '{key}'")
        return feature

    def start_all(self):
        for feature in self.features.values():
            feature.start()

    def stop_all(self):
        for feature in self.features.values():
            feature.stop()

    def status(self):
        return {key: feature.get_status() for key, feature in self.features.items()}
