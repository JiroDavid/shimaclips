from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from live import LiveClips
from store import Store
from twitch import TwitchClient

if TYPE_CHECKING:
    from ask.transcription import TranscriptionManager


@dataclass
class Services:
    store: Store
    live: LiveClips | None
    twitch: Callable[[], TwitchClient] | None
    transcriber: "TranscriptionManager | None" = None

    @property
    def db_path(self) -> Path:
        return self.store.path
