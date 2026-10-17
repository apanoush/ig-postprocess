"""Command-line entry point for the Instagram export post-processor."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

from .config import Config, load_config
from .organize import copy_export, load_result, organize
from .report import write_reports


def _common_parser() -> argparse.ArgumentParser:
    """Return a parent parser with options accepted before and after a subcommand."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-s",
        "--source",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="input export folder, containing media/ and your_instagram_activity/",
    )
    common.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="folder for the copy and organised tree",
    )
    common.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help="enable debug logging",
    )
    return common


def _build_parser() -> argparse.ArgumentParser:
    common = _common_parser()
    parser = argparse.ArgumentParser(
        prog="ig-postprocess",
        description="Organise an Instagram data export into per-post media folders.",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command")

    copy_cmd = sub.add_parser(
        "copy", parents=[common], help="copy the read-only export into the output folder"
    )
    copy_cmd.add_argument("--force", action="store_true", help="overwrite an existing copy")

    sub.add_parser("organize", parents=[common], help="organise an existing copy and write reports")

    sub.add_parser("report", parents=[common], help="regenerate reports from an organised tree")

    run_cmd = sub.add_parser("run", parents=[common], help="copy (if needed), organise and report")
    run_cmd.add_argument("--force", action="store_true", help="overwrite an existing copy")
    return parser


def _resolve_config(args: argparse.Namespace) -> Config:
    """Load ``config.toml`` and apply the ``--source`` / ``--output`` overrides."""
    config = load_config()
    overrides: dict[str, Path] = {}
    source = getattr(args, "source", None)
    if source is not None:
        overrides["source_export"] = Path(source).expanduser().resolve()
    output = getattr(args, "output", None)
    if output is not None:
        overrides["output_dir"] = Path(output).expanduser().resolve()
    return replace(config, **overrides) if overrides else config


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
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    config = _resolve_config(args)
    command = args.command or "run"

    if (
        command in ("copy", "run")
        and getattr(args, "source", None) is not None
        and not config.source_export.is_dir()
    ):
        parser.error(f"source export folder not found: {config.source_export}")

    if command == "copy":
        return _cmd_copy(config, getattr(args, "force", False))
    if command == "organize":
        return _cmd_organize(config)
    if command == "report":
        return _cmd_report(config)
    if command == "run":
        _cmd_copy(config, getattr(args, "force", False))
        return _cmd_organize(config)
    parser.error(f"unknown command: {command}")  # pragma: no cover
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
