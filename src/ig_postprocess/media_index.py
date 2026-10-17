"""Hash export media and resolve duplicate content to a single preferred file.

The export keeps two media layouts (legacy ``media/posts/<id>.<ext>`` and newer
``media/posts/<YYYYMM>/<id>.<ext>``). The same image therefore exists under two
different file names. :class:`MediaIndex` maps every referenced URI to its MD5
digest so that duplicates can be collapsed by content.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

_READ_CHUNK = 1 << 20


def short_md5(path: Path, chunk_size: int = _READ_CHUNK) -> str:
    """Return the MD5 hex digest of *path*, read in chunks."""
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def layout_rank(uri: str) -> int:
    """Preference rank of a URI's folder layout (lower is preferred)."""
    parts = uri.split("/")
    if parts[:2] == ["media", "posts"]:
        # Newer export layout nests media one level deeper, by year-month.
        return 0 if len(parts) == 4 else 1
    if parts[:2] == ["media", "archived_posts"]:
        return 2
    if parts[:2] == ["media", "stories"]:
        return 3
    return 4


@dataclass(frozen=True)
class FileInfo:
    """Hashing result for a single media file."""

    uri: str
    md5: str
    size: int
    rank: int


class MediaIndex:
    """Lazily hashes files under an export root and answers content queries."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._files: dict[str, FileInfo] = {}

    def add(self, uri: str) -> FileInfo | None:
        """Hash *uri* (relative to the export root) and cache the result."""
        if uri in self._files:
            return self._files[uri]
        path = self.root / uri
        if not path.is_file():
            return None
        info = FileInfo(
            uri=uri, md5=short_md5(path), size=path.stat().st_size, rank=layout_rank(uri)
        )
        self._files[uri] = info
        return info

    def add_all(self, uris: Iterable[str]) -> None:
        for uri in uris:
            self.add(uri)

    def get(self, uri: str) -> FileInfo | None:
        return self._files.get(uri) or self.add(uri)

    def digest(self, uri: str) -> str:
        """Return the MD5 of *uri*, raising :class:`KeyError` if it is missing."""
        info = self.get(uri)
        if info is None:
            raise KeyError(f"media file not found in export: {uri}")
        return info.md5

    def has(self, uri: str) -> bool:
        return (self.root / uri).is_file()

    def preferred(self, uris: Iterable[str]) -> str:
        """Return the best physical URI among *uris* (assumed same content)."""
        candidates = [u for u in uris if self.has(u)]
        if not candidates:
            raise KeyError("none of the candidate URIs exist in the export")
        return min(candidates, key=lambda u: (layout_rank(u), u))

    def files(self) -> tuple[FileInfo, ...]:
        """Return every hashed file, sorted by URI."""
        return tuple(self._files[uri] for uri in sorted(self._files))

    def iter_files(self, subdir: str) -> Iterator[FileInfo]:
        """Yield :class:`FileInfo` for every file under ``<root>/<subdir>``."""
        base = self.root / subdir
        for path in sorted(base.rglob("*")):
            if path.is_file():
                uri = path.relative_to(self.root).as_posix()
                info = self.add(uri)
                if info is not None:
                    yield info
