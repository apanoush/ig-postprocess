"""Plan and perform the on-disk organisation of a copied export."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .crosscheck import match_entries
from .export_reader import (
    LegacyPost,
    MediaRef,
    RawEntry,
    read_archived_posts,
    read_legacy_posts,
    read_new_entries,
    read_profile_photos,
    read_stories,
)
from .media_index import MediaIndex

log = logging.getLogger("ig_postprocess")

CATEGORY_POSTS = "posts"
CATEGORY_ARCHIVED = "archived_posts"
CATEGORY_STORIES = "stories"
CATEGORY_PROFILE = "profile"


@dataclass(frozen=True)
class PlannedMedia:
    """A media item placed inside a post folder."""

    filename: str
    uri: str
    md5: str


@dataclass(frozen=True)
class PlannedPost:
    """A post folder and the media that go into it."""

    folder: str
    category: str
    fbid: str
    timestamp: int
    caption: str
    caption_source: str
    media: tuple[PlannedMedia, ...]


@dataclass(frozen=True)
class PlannedSingle:
    """A story or profile-photo item with its own folder."""

    folder: str
    category: str
    timestamp: int
    caption: str
    media: tuple[PlannedMedia, ...]


@dataclass
class RunStats:
    """Counts gathered while organising, used for the summary report."""

    posts: int = 0
    archived_posts: int = 0
    stories: int = 0
    profile_photos: int = 0
    media_placed: int = 0
    duplicates_moved: int = 0
    orphan_files: int = 0


@dataclass
class OrganizeResult:
    """Everything the report step needs after media have been moved."""

    posts: list[PlannedPost]
    singles: list[PlannedSingle]
    stats: RunStats
    index: MediaIndex
    moved: set[str]


def _basename_stem(uri: str) -> str:
    return Path(uri).name.rsplit(".", 1)[0]


def _format_date(timestamp: int, date_format: str) -> str:
    if timestamp <= 0:
        return "0000-00-00"
    return datetime.fromtimestamp(timestamp, tz=UTC).strftime(date_format)


def _candidates_by_digest(
    entry: RawEntry, legacy: LegacyPost, index: MediaIndex
) -> dict[str, list[str]]:
    """Map each content digest to every physical URI that provides it.

    Both the newer entry and the legacy post are considered, so a content that
    exists under two layouts exposes both copies as candidates.
    """
    candidates: dict[str, list[str]] = {}

    def add(uri: str) -> None:
        bucket = candidates.setdefault(index.digest(uri), [])
        if uri not in bucket:
            bucket.append(uri)

    for uri in entry.media_uris:
        add(uri)
    for ref in legacy.media:
        add(ref.uri)
    return candidates


def _ordered_digests(
    entry: RawEntry,
    legacy: LegacyPost,
    index: MediaIndex,
    candidates: dict[str, list[str]],
) -> list[str]:
    """Return content digests in display order.

    Legacy media keep their authoritative carousel order. A cover image the
    newer schema adds and that is not already present is prepended (the export
    names it after the post id); anything else (subtitles) is appended.
    """
    legacy_order: list[str] = []
    legacy_seen: set[str] = set()
    for ref in legacy.media:
        digest = index.digest(ref.uri)
        if digest not in legacy_seen:
            legacy_seen.add(digest)
            legacy_order.append(digest)

    extras_order: list[str] = []
    extras_seen: set[str] = set()
    for uri in entry.media_uris:
        digest = index.digest(uri)
        if digest in legacy_seen or digest in extras_seen:
            continue
        extras_seen.add(digest)
        extras_order.append(digest)

    def is_cover(digest: str) -> bool:
        return any(_basename_stem(uri) == entry.fbid for uri in candidates[digest])

    covers = [digest for digest in extras_order if is_cover(digest)]
    rest = [digest for digest in extras_order if digest not in covers]
    return covers + legacy_order + rest


def _planned_media(
    digests: list[str], candidates: dict[str, list[str]], index: MediaIndex
) -> tuple[PlannedMedia, ...]:
    """Pick the preferred file for each digest, preserving order."""
    media: list[PlannedMedia] = []
    for position, digest in enumerate(digests, start=1):
        uri = index.preferred(candidates[digest])
        media.append(PlannedMedia(filename=f"{position:02d}_{Path(uri).name}", uri=uri, md5=digest))
    return tuple(media)


def plan_posts(
    entries: list[RawEntry],
    legacy_posts: list[LegacyPost],
    archived_posts: list[LegacyPost],
    index: MediaIndex,
    date_format: str,
) -> list[PlannedPost]:
    """Build the per-post plan, cross-checking the two schemas."""
    legacy_all = list(legacy_posts) + list(archived_posts)
    match = match_entries(entries, legacy_all, index)
    regular_count = len(legacy_posts)

    planned: list[PlannedPost] = []
    for legacy_index, legacy in enumerate(legacy_all):
        entry = entries[match.legacy_to_entry[legacy_index]]
        category = CATEGORY_ARCHIVED if legacy_index >= regular_count else CATEGORY_POSTS

        caption = legacy.caption
        caption_source = legacy.source
        if not caption and entry.caption:
            caption = entry.caption
            caption_source = entry.source

        timestamp = legacy.timestamp or entry.timestamp
        fbid = entry.fbid
        folder = f"{_format_date(timestamp, date_format)}_{fbid}"

        candidates = _candidates_by_digest(entry, legacy, index)
        digests = _ordered_digests(entry, legacy, index, candidates)
        planned.append(
            PlannedPost(
                folder=folder,
                category=category,
                fbid=fbid,
                timestamp=timestamp,
                caption=caption,
                caption_source=caption_source,
                media=_planned_media(digests, candidates, index),
            )
        )
    return planned


def plan_singles(
    refs: list[MediaRef],
    category: str,
    index: MediaIndex,
    date_format: str,
) -> list[PlannedSingle]:
    """Build one folder per story / profile item, in chronological order."""
    planned: list[PlannedSingle] = []
    for ref in sorted(refs, key=lambda r: (r.creation_timestamp or 0, r.uri)):
        if not index.has(ref.uri):
            log.warning("skipping missing %s media: %s", category, ref.uri)
            continue
        timestamp = ref.creation_timestamp or 0
        date = _format_date(timestamp, date_format)
        folder = f"{date}_{_basename_stem(ref.uri)}"
        digest = index.digest(ref.uri)
        media = _planned_media([digest], {digest: [ref.uri]}, index)
        planned.append(
            PlannedSingle(
                folder=folder,
                category=category,
                timestamp=timestamp,
                caption=ref.title,
                media=tuple(media),
            )
        )
    return planned


def _move_media(copy_dir: Path, planned_media: PlannedMedia, target_dir: Path) -> None:
    source = copy_dir / planned_media.uri
    if not source.is_file():
        raise FileNotFoundError(f"expected media is missing: {source}")
    shutil.move(str(source), str(target_dir / planned_media.filename))


def _write_post_folder(
    copy_dir: Path,
    target_dir: Path,
    folder: str,
    category: str,
    fbid: str,
    timestamp: int,
    caption: str,
    caption_source: str,
    media: tuple[PlannedMedia, ...],
    date_format: str,
) -> set[str]:
    post_dir = target_dir / folder
    post_dir.mkdir(parents=True, exist_ok=True)
    moved: set[str] = set()
    for item in media:
        _move_media(copy_dir, item, post_dir)
        moved.add(item.uri)

    if caption:
        (post_dir / "caption.txt").write_text(caption + "\n", encoding="utf-8")

    metadata = {
        "fbid": fbid,
        "timestamp": timestamp,
        "date": _format_date(timestamp, date_format),
        "category": category,
        "caption": caption,
        "caption_source": caption_source,
        "media": [
            {"filename": item.filename, "original_uri": item.uri, "md5": item.md5} for item in media
        ],
    }
    (post_dir / "post.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return moved


def copy_export(config: Config, *, force: bool = False) -> Path:
    """Copy the read-only export into :attr:`Config.copy_dir`."""
    source = config.source_export
    dest = config.copy_dir
    if dest.exists():
        if not force:
            raise FileExistsError(f"{dest} already exists (use --force to overwrite)")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for sub in (config.media_dirname, config.activity_dirname):
        src = source / sub
        if not src.is_dir():
            raise FileNotFoundError(f"missing source subdirectory: {src}")
        shutil.copytree(src, dest / sub)
    log.info("copied export to %s", dest)
    return dest


def build_index(copy_dir: Path, media_dirname: str) -> MediaIndex:
    """Hash every media file in the copied export."""
    index = MediaIndex(copy_dir)
    count = 0
    for _ in index.iter_files(media_dirname):
        count += 1
    log.info("hashed %d media files", count)
    return index


def organize(config: Config) -> OrganizeResult:
    """Move media into per-post folders inside the copied export."""
    copy_dir = config.copy_dir
    if not copy_dir.is_dir():
        raise FileNotFoundError(f"copied export not found: {copy_dir} (run `copy` first)")

    index = build_index(copy_dir, config.media_dirname)

    activity = copy_dir / config.activity_dirname / "media"
    entries = read_new_entries(activity / "posts.json")
    legacy_posts = read_legacy_posts(activity / "posts_1.json")
    archived_posts = read_archived_posts(activity / "archived_posts.json")
    stories = read_stories(activity / "stories.json")
    profile = read_profile_photos(activity / "profile_photos.json")

    planned_posts = plan_posts(entries, legacy_posts, archived_posts, index, config.date_format)
    planned_stories = plan_singles(stories, CATEGORY_STORIES, index, config.date_format)
    planned_profile = plan_singles(profile, CATEGORY_PROFILE, index, config.date_format)

    stats = RunStats(
        posts=sum(1 for p in planned_posts if p.category == CATEGORY_POSTS),
        archived_posts=sum(1 for p in planned_posts if p.category == CATEGORY_ARCHIVED),
        stories=len(planned_stories),
        profile_photos=sum(len(s.media) for s in planned_profile),
    )
    log.info(
        "planned %d posts, %d archived, %d stories, %d profile",
        stats.posts,
        stats.archived_posts,
        stats.stories,
        stats.profile_photos,
    )

    moved: set[str] = set()
    for post in planned_posts:
        moved |= _write_post_folder(
            copy_dir,
            copy_dir / post.category,
            post.folder,
            post.category,
            post.fbid,
            post.timestamp,
            post.caption,
            post.caption_source,
            post.media,
            config.date_format,
        )
    for single in planned_stories + planned_profile:
        moved |= _write_post_folder(
            copy_dir,
            copy_dir / single.category,
            single.folder,
            single.category,
            fbid="",
            timestamp=single.timestamp,
            caption=single.caption,
            caption_source="stories.json"
            if single.category == CATEGORY_STORIES
            else "profile_photos.json",
            media=single.media,
            date_format=config.date_format,
        )

    stats.media_placed = len(moved)

    # Any media file that was never placed is a duplicate or an orphan.
    duplicates_root = copy_dir / config.duplicates_dirname
    for info in index.iter_files(config.media_dirname):
        if info.uri in moved:
            continue
        target = duplicates_root / info.uri
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(copy_dir / info.uri), str(target))
        stats.duplicates_moved += 1
    stats.orphan_files = stats.duplicates_moved

    # Drop the now-empty raw media tree.
    raw_media = copy_dir / config.media_dirname
    if raw_media.is_dir():
        shutil.rmtree(raw_media)

    return OrganizeResult(
        posts=planned_posts,
        singles=planned_stories + planned_profile,
        stats=stats,
        index=index,
        moved=moved,
    )


def load_result(config: Config) -> OrganizeResult:
    """Rebuild an :class:`OrganizeResult` from an already-organised tree.

    Used by the ``report`` subcommand so reports can be regenerated without
    touching the source export again.
    """
    copy_dir = config.copy_dir
    index = MediaIndex(copy_dir)
    subdirs = (
        CATEGORY_POSTS,
        CATEGORY_ARCHIVED,
        CATEGORY_STORIES,
        CATEGORY_PROFILE,
        config.duplicates_dirname,
    )
    for sub in subdirs:
        if (copy_dir / sub).is_dir():
            for _ in index.iter_files(sub):
                pass

    posts: list[PlannedPost] = []
    singles: list[PlannedSingle] = []
    for category in (CATEGORY_POSTS, CATEGORY_ARCHIVED):
        posts.extend(_load_post_folders(copy_dir / category, category))
    for category in (CATEGORY_STORIES, CATEGORY_PROFILE):
        singles.extend(_load_single_folders(copy_dir / category, category))

    moved = {item.uri for post in posts for item in post.media}
    moved |= {item.uri for single in singles for item in single.media}
    stats = RunStats(
        posts=sum(1 for p in posts if p.category == CATEGORY_POSTS),
        archived_posts=sum(1 for p in posts if p.category == CATEGORY_ARCHIVED),
        stories=sum(1 for s in singles if s.category == CATEGORY_STORIES),
        profile_photos=sum(len(s.media) for s in singles if s.category == CATEGORY_PROFILE),
        media_placed=len(moved),
    )
    return OrganizeResult(posts=posts, singles=singles, stats=stats, index=index, moved=moved)


def _load_media(meta: dict) -> tuple[PlannedMedia, ...]:
    return tuple(
        PlannedMedia(filename=str(m["filename"]), uri=str(m["original_uri"]), md5=str(m["md5"]))
        for m in meta.get("media", [])
    )


def _load_post_folders(root: Path, category: str) -> list[PlannedPost]:
    posts: list[PlannedPost] = []
    if not root.is_dir():
        return posts
    for meta_path in sorted(root.glob("*/post.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        posts.append(
            PlannedPost(
                folder=meta_path.parent.name,
                category=category,
                fbid=str(meta.get("fbid", "")),
                timestamp=int(meta.get("timestamp") or 0),
                caption=str(meta.get("caption", "")),
                caption_source=str(meta.get("caption_source", "")),
                media=_load_media(meta),
            )
        )
    return posts


def _load_single_folders(root: Path, category: str) -> list[PlannedSingle]:
    singles: list[PlannedSingle] = []
    if not root.is_dir():
        return singles
    for meta_path in sorted(root.glob("*/post.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        singles.append(
            PlannedSingle(
                folder=meta_path.parent.name,
                category=category,
                timestamp=int(meta.get("timestamp") or 0),
                caption=str(meta.get("caption", "")),
                media=_load_media(meta),
            )
        )
    return singles
