"""Command-line entry point for the Instagram export post-processor."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import Config, load_config
from .organize import copy_export, load_result, organize
from .report import write_reports


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ig-postprocess",
        description="Organise an Instagram data export into per-post media folders.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    sub = parser.add_subparsers(dest="command")

    copy_cmd = sub.add_parser("copy", help="copy the read-only export into the work dir")
    copy_cmd.add_argument("--force", action="store_true", help="overwrite an existing copy")

    sub.add_parser("organize", help="organise an existing copy and write reports")

    sub.add_parser("report", help="regenerate reports from an organised tree")

    run_cmd = sub.add_parser("run", help="copy (if needed), organise and report")
    run_cmd.add_argument("--force", action="store_true", help="overwrite an existing copy")
    return parser


def _cmd_copy(config: Config, force: bool) -> int:
    destination = config.copy_dir
    if destination.exists() and not force:
        logging.getLogger("ig_postprocess").info("copy already present at %s", destination)
        return 0
    copy_export(config, force=force)
    return 0


def _cmd_organize(config: Config) -> int:
    result = organize(config)
    report = write_reports(config, result)
    summary = report.summary
    print(
        f"organised {result.stats.posts} posts, {result.stats.archived_posts} archived, "
        f"{result.stats.stories} stories, {result.stats.profile_photos} profile photos"
    )
    print(
        f"moved {summary.redundant_files} duplicate files to "
        f"{config.duplicates_dirname}/ ({summary.reclaimable_bytes / 1e6:.1f} MB)"
    )
    print(f"reports written to {config.copy_dir}")
    return 0


def _cmd_report(config: Config) -> int:
    result = load_result(config)
    write_reports(config, result)
    print(f"regenerated reports in {config.copy_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; returns a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    config = load_config()
    command = args.command or "run"

    if command == "copy":
        return _cmd_copy(config, args.force)
    if command == "organize":
        return _cmd_organize(config)
    if command == "report":
        return _cmd_report(config)
    if command == "run":
        _cmd_copy(config, args.force)
        return _cmd_organize(config)
    parser.error(f"unknown command: {command}")  # pragma: no cover
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
