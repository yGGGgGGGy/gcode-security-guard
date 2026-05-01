"""Log source adapters — file tail, journald stub, stdin."""

from __future__ import annotations

import os
from typing import Any

from .models import SourceType


class FileSource:
    """tail -f style incremental reader for a single file."""

    def __init__(self, path: str):
        self.path = path
        self._pos = os.path.getsize(path) if os.path.isfile(path) else 0

    def read_lines(self) -> list[str]:
        """Return new lines since last read."""
        try:
            with open(self.path, "r") as f:
                f.seek(self._pos)
                lines = f.readlines()
                self._pos = f.tell()
            return [l.rstrip("\n").rstrip("\r") for l in lines]
        except FileNotFoundError:
            return []

    def reset(self) -> None:
        self._pos = 0


SOURCE_FACTORY: dict[SourceType, Any] = {
    SourceType.FILE: FileSource,
}
