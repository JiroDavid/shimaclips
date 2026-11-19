from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from live import LiveClips
from store import Store
from twitch import TwitchClient


@dataclass
class Services:
    store: Store
    live: LiveClips | None
    twitch: Callable[[], TwitchClient] | None

    @property
    def db_path(self) -> Path:
        return self.store.path
