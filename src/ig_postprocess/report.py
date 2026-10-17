"""Write the index, duplicate report and human summary for a finished run."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .media_index import FileInfo
from .organize import OrganizeResult, PlannedPost, PlannedSingle

_MEDIA_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_MEDIA_VIDEO_EXT = {".mp4", ".mov", ".webm"}
_MEDIA_SUBTITLE_EXT = {".srt", ".vtt"}


@dataclass(frozen=True)
class IndexRow:
    """One row of ``index.csv``."""

    category: str
    folder: str
    fbid: str
    timestamp: int
    datetime_utc: str
    media_count: int
    images: int
    videos: int
    subtitles: int
    has_caption: bool
    caption: str
    caption_source: str


@dataclass(frozen=True)
class DuplicateGroup:
    """A set of byte-identical files."""

    md5: str
    size_bytes: int
    kept: list[str]
    dropped: list[str]


@dataclass(frozen=True)
class DuplicatesSummary:
    """Aggregate numbers for the duplicate report."""

    duplicate_groups: int
    redundant_files: int
    reclaimable_bytes: int
    cross_post_groups: int


@dataclass(frozen=True)
class DuplicatesReport:
    """The full ``duplicates_report.json`` structure."""

    summary: DuplicatesSummary
    groups: list[DuplicateGroup]


def _kind(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in _MEDIA_IMAGE_EXT:
        return "image"
    if ext in _MEDIA_VIDEO_EXT:
        return "video"
    if ext in _MEDIA_SUBTITLE_EXT:
        return "subtitle"
    return "other"


def _iso(timestamp: int) -> str:
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


def _row(planned: PlannedPost | PlannedSingle, fbid: str, caption_source: str) -> IndexRow:
    kinds = [_kind(item.filename) for item in planned.media]
    return IndexRow(
        category=planned.category,
        folder=planned.folder,
        fbid=fbid,
        timestamp=planned.timestamp,
        datetime_utc=_iso(planned.timestamp),
        media_count=len(planned.media),
        images=kinds.count("image"),
        videos=kinds.count("video"),
        subtitles=kinds.count("subtitle"),
        has_caption=bool(planned.caption.strip()),
        caption=planned.caption.replace("\n", " ").replace("\r", " ").strip(),
        caption_source=caption_source,
    )


def write_index(path: Path, result: OrganizeResult) -> None:
    """Write ``index.csv`` describing every organised folder."""
    rows = [_row(post, post.fbid, post.caption_source) for post in result.posts]
    rows += [_row(single, "", f"{single.category}.json") for single in result.singles]
    rows.sort(key=lambda row: (row.timestamp, row.category), reverse=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def write_duplicates_report(path: Path, result: OrganizeResult) -> DuplicatesReport:
    """Write ``duplicates_report.json`` and return the same structure."""
    groups: dict[str, list[FileInfo]] = defaultdict(list)
    for info in result.index.files():
        groups[info.md5].append(info)

    duplicate_groups: list[DuplicateGroup] = []
    redundant_files = 0
    reclaimable = 0
    cross_post_groups = 0
    for md5, infos in sorted(groups.items()):
        if len(infos) < 2:
            continue
        kept = sorted(i.uri for i in infos if i.uri in result.moved)
        dropped = sorted(i.uri for i in infos if i.uri not in result.moved)
        if len(kept) > 1:
            cross_post_groups += 1
        redundant_files += len(dropped)
        reclaimable += sum(i.size for i in infos if i.uri not in result.moved)
        duplicate_groups.append(
            DuplicateGroup(
                md5=md5,
                size_bytes=max(i.size for i in infos),
                kept=kept,
                dropped=dropped,
            )
        )

    report = DuplicatesReport(
        summary=DuplicatesSummary(
            duplicate_groups=len(duplicate_groups),
            redundant_files=redundant_files,
            reclaimable_bytes=reclaimable,
            cross_post_groups=cross_post_groups,
        ),
        groups=duplicate_groups,
    )
    path.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def write_summary(path: Path, result: OrganizeResult, report: DuplicatesReport) -> None:
    """Write a short human-readable ``summary.md``."""
    stats = result.stats
    summary = report.summary
    lines = [
        "# Instagram export post-processing summary",
        "",
        "## Organised folders",
        "",
        f"- regular posts: {stats.posts}",
        f"- archived posts: {stats.archived_posts}",
        f"- stories: {stats.stories}",
        f"- profile photos: {stats.profile_photos}",
        f"- media files placed: {stats.media_placed}",
        "",
        "## Duplicates",
        "",
        f"- duplicate content groups: {summary.duplicate_groups}",
        f"- redundant copies moved to `_duplicates/`: {summary.redundant_files}",
        f"- reclaimable space: {summary.reclaimable_bytes / 1e6:.1f} MB",
        f"- images reused across different posts: {summary.cross_post_groups}",
        "",
        "Files in `_duplicates/` are byte-identical to a file kept in a post folder",
        "and can be deleted.",
        "",
        "## Schema note",
        "",
        "`posts.json` (newer, nested, localized) was cross-checked against",
        "`posts_1.json` + `archived_posts.json` (legacy, clean). Media order and",
        "captions come from the legacy files; the newer schema supplied extra",
        "cover images and `.srt` subtitles.",
        "",
        "## Run stats",
        "",
        "```json",
        json.dumps(asdict(stats), indent=2),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_reports(config: Config, result: OrganizeResult) -> DuplicatesReport:
    """Write every report file at the root of the copied export."""
    root = config.copy_dir
    write_index(root / config.index_name, result)
    report = write_duplicates_report(root / config.duplicates_report_name, result)
    write_summary(root / config.summary_name, result, report)
    return report
