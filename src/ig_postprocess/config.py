"""Configuration for the Instagram export post-processor.

Tunable parameters live in ``config.toml`` next to the project root and are
loaded into the frozen :class:`Config` dataclass. Missing keys fall back to the
defaults declared here, so the tool runs with no configuration at all.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

# ``config.py`` -> ``ig_postprocess`` -> ``src`` -> project root (``post_processing``).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    """Paths and naming knobs for the whole pipeline."""

    #: Root of the original, read-only export.
    source_export: Path = PROJECT_ROOT.parent / "instagram_export"
    #: Where the copy and the organised tree are written.
    workdir: Path = PROJECT_ROOT
    #: Name of the copied export inside :attr:`workdir`.
    copy_name: str = "instagram_export"
    #: Explicit destination for the copy; overrides :attr:`workdir` / :attr:`copy_name`.
    output_dir: Path | None = None
    #: ``strftime`` format used for post folder names.
    date_format: str = "%Y-%m-%d"
    #: Directory that collects duplicate / orphaned media.
    duplicates_dirname: str = "_duplicates"
    #: Report file names (written at the root of the copied export).
    index_name: str = "index.csv"
    summary_name: str = "summary.md"
    duplicates_report_name: str = "duplicates_report.json"
    #: Subfolders of the export that make up the source tree to copy.
    media_dirname: str = "media"
    activity_dirname: str = "your_instagram_activity"

    @property
    def copy_dir(self) -> Path:
        """Absolute path of the copied export (also the output tree root)."""
        if self.output_dir is not None:
            return self.output_dir
        return self.workdir / self.copy_name


def load_config(path: Path | None = None) -> Config:
    """Load :class:`Config` from ``path`` (defaults to ``<root>/config.toml``)."""
    default = Config()
    path = path or PROJECT_ROOT / "config.toml"
    if not path.is_file():
        return default
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    def text(key: str, fallback: str) -> str:
        value = raw.get(key)
        return value if isinstance(value, str) else fallback

    def directory(key: str, fallback: Path) -> Path:
        value = raw.get(key)
        return Path(value) if isinstance(value, str) else fallback

    def optional_directory(key: str, fallback: Path | None) -> Path | None:
        value = raw.get(key)
        return Path(value) if isinstance(value, str) else fallback

    return Config(
        source_export=directory("source_export", default.source_export),
        workdir=directory("workdir", default.workdir),
        copy_name=text("copy_name", default.copy_name),
        output_dir=optional_directory("output_dir", default.output_dir),
        date_format=text("date_format", default.date_format),
        duplicates_dirname=text("duplicates_dirname", default.duplicates_dirname),
        index_name=text("index_name", default.index_name),
        summary_name=text("summary_name", default.summary_name),
        duplicates_report_name=text("duplicates_report_name", default.duplicates_report_name),
        media_dirname=text("media_dirname", default.media_dirname),
        activity_dirname=text("activity_dirname", default.activity_dirname),
    )
