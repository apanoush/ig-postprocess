"""Read Instagram export JSON files into typed, text-repaired structures.

Two schema generations coexist in the export:

* the legacy schema (``posts_1.json``, ``archived_posts.json``, ``stories.json``,
  ``profile_photos.json``) with flat ``media`` lists, and
* the newer schema (``posts.json``, ``other_content.json``, ``saved/*``) whose
  data is nested under localized ``label_values``.

Only :func:`read_new_entry` needs to understand the localized labels, and only
for the caption fallback; media references are collected structurally so that a
change of export language does not break the reader.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .textfix import fix_mojibake

#: Labels that carry the post caption in the newer schema (German export).
CAPTION_LABELS: tuple[str, ...] = ("Untertitel", "Titel")


@dataclass(frozen=True)
class MediaRef:
    """A single media item referenced by a post."""

    uri: str
    creation_timestamp: int | None = None
    title: str = ""


@dataclass(frozen=True)
class LegacyPost:
    """A post as described by the legacy schema."""

    media: tuple[MediaRef, ...]
    timestamp: int
    caption: str
    source: str


@dataclass(frozen=True)
class RawEntry:
    """A post as described by the newer, nested schema."""

    fbid: str
    timestamp: int
    media_uris: tuple[str, ...]
    caption: str
    source: str


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_dicts(obj: Any) -> Iterator[dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _iter_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _iter_dicts(value)


def _collect_uris(obj: Any) -> tuple[str, ...]:
    """Return every ``uri`` value in *obj*, in document order, de-duplicated."""
    seen: set[str] = set()
    uris: list[str] = []
    for node in _iter_dicts(obj):
        uri = node.get("uri")
        if isinstance(uri, str) and uri not in seen:
            seen.add(uri)
            uris.append(uri)
    return tuple(uris)


def _media_ref(node: dict[str, Any]) -> MediaRef:
    ts = node.get("creation_timestamp")
    return MediaRef(
        uri=str(node["uri"]),
        creation_timestamp=int(ts) if isinstance(ts, int) else None,
        title=fix_mojibake(str(node.get("title", ""))),
    )


def _entry_caption(node: dict[str, Any]) -> str:
    label_values = node.get("label_values")
    if not isinstance(label_values, list):
        return ""
    for wanted in CAPTION_LABELS:
        for item in label_values:
            if not isinstance(item, dict):
                continue
            if fix_mojibake(str(item.get("label", ""))) == wanted:
                value = item.get("value")
                if isinstance(value, str) and value.strip():
                    return fix_mojibake(value)
    return ""


def read_new_entries(path: Path) -> list[RawEntry]:
    """Read a newer-schema file (a list of entries, or a single entry object)."""
    data = _load(path)
    if isinstance(data, dict):
        items: list[Any] = [data]
    elif isinstance(data, list):
        items = data
    else:  # pragma: no cover - defensive
        raise ValueError(f"unexpected JSON root in {path}: {type(data).__name__}")

    entries: list[RawEntry] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        entries.append(
            RawEntry(
                fbid=str(item.get("fbid", "")),
                timestamp=int(item.get("timestamp") or 0),
                media_uris=_collect_uris(item),
                caption=_entry_caption(item),
                source=path.name,
            )
        )
    return entries


def read_legacy_posts(path: Path) -> list[LegacyPost]:
    """Read ``posts_1.json``: a list of posts with flat ``media`` lists."""
    posts: list[LegacyPost] = []
    for item in _load(path):
        if not isinstance(item, dict):
            continue
        media = tuple(
            _media_ref(m) for m in item.get("media", []) if isinstance(m, dict) and "uri" in m
        )
        posts.append(
            LegacyPost(
                media=media,
                timestamp=int(item.get("creation_timestamp") or 0),
                caption=fix_mojibake(str(item.get("title", ""))),
                source=path.name,
            )
        )
    return posts


def read_archived_posts(path: Path) -> list[LegacyPost]:
    """Read ``archived_posts.json`` (``ig_archived_post_media`` list)."""
    data = _load(path)
    posts: list[LegacyPost] = []
    for item in data.get("ig_archived_post_media", []):
        if not isinstance(item, dict):
            continue
        media = tuple(
            _media_ref(m) for m in item.get("media", []) if isinstance(m, dict) and "uri" in m
        )
        timestamp = media[0].creation_timestamp if media else None
        caption = media[0].title if media else ""
        posts.append(
            LegacyPost(
                media=media,
                timestamp=int(timestamp or 0),
                caption=caption,
                source=path.name,
            )
        )
    return posts


def read_stories(path: Path) -> list[MediaRef]:
    """Read ``stories.json`` (``ig_stories`` list)."""
    data = _load(path)
    return [_media_ref(m) for m in data.get("ig_stories", []) if isinstance(m, dict) and "uri" in m]


def read_profile_photos(path: Path) -> list[MediaRef]:
    """Read ``profile_photos.json`` (``ig_profile_picture`` list)."""
    data = _load(path)
    return [
        _media_ref(m)
        for m in data.get("ig_profile_picture", [])
        if isinstance(m, dict) and "uri" in m
    ]
