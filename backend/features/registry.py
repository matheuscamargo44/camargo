"""Registers the available features. Adding a new module means adding it here
and nothing else needs to change in the API or the client.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from core.config import load_config
from core.lcu_client import LCUClient
from features.aram_bench_swap import AramBenchSwap
from features.auto_accept import AutoAccept
from features.auto_honor import AutoHonor
from features.auto_play_again import AutoPlayAgain
from features.customization import Background, Badges, ClientIcon, ProfileIcon, StatusMessage
from features.dodge import Dodge
from features.friend_requests import FriendRequestsManager
from features.instalock import Instalock
from features.autoban import AutoBan
from features.loot import MassDisenchant
from features.party_invite import AutoPartyInvite
from features.practice_tool import PracticeTool5v5
from features.presence_status import PresenceStatus
from features.random_skin import RandomSkinPicker
from features.ranked_presence import RankedPresence
from features.social import ChatToggle, RemoveFriends, RestartUX
from features.titles import ChallengeTitles

FEATURE_CLASSES = [
    # Automation
    AutoAccept,
    Instalock,
    AutoBan,
    AutoPlayAgain,
    AutoPartyInvite,
    AutoHonor,
    Dodge,
    AramBenchSwap,
    RandomSkinPicker,
    PracticeTool5v5,
    # Customization
    Background,
    ProfileIcon,
    ClientIcon,
    Badges,
    ChallengeTitles,
    MassDisenchant,
    StatusMessage,
    # Social
    ChatToggle,
    PresenceStatus,
    RankedPresence,
    FriendRequestsManager,
    RemoveFriends,
    RestartUX,
]


logger = logging.getLogger(__name__)


class FeatureRegistry:
    def __init__(self, on_event=None):
        self.lcu = LCUClient()
        self.config = load_config()
        self.on_event = on_event or (lambda _level, _message: None)
        self.features = {
            cls.key: cls(self.lcu, self.config, self.on_event) for cls in FEATURE_CLASSES
        }
        # Nine of these statuses each make their own blocking call to the
        # client; done in series they add up to most of a /features response.
        self._status_pool = ThreadPoolExecutor(
            max_workers=8, thread_name_prefix="camargo-status"
        )

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
        self._status_pool.shutdown(wait=False)

    def _safe_status(self, feature):
        try:
            return feature.get_status()
        except Exception:
            # One misbehaving feature must not take the whole status call down
            logger.exception("get_status failed for '%s'", feature.key)
            return {"key": feature.key}

    def status(self):
        features = list(self.features.values())
        results = self._status_pool.map(self._safe_status, features)
        return {feature.key: status for feature, status in zip(features, results)}
