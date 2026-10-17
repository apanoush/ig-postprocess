from __future__ import annotations

from pathlib import Path

import pytest

from ig_postprocess import cli
from ig_postprocess.config import Config


def _parser():
    return cli._build_parser()


def test_source_and_output_accepted_after_subcommand() -> None:
    args = _parser().parse_args(["run", "-s", "/in", "-o", "/out"])
    assert args.source == "/in"
    assert args.output == "/out"


def test_source_and_output_accepted_before_subcommand() -> None:
    args = _parser().parse_args(["-s", "/in", "run", "-o", "/out"])
    assert args.source == "/in"
    assert args.output == "/out"


def test_verbose_accepted_before_and_after() -> None:
    assert getattr(_parser().parse_args(["-v", "run"]), "verbose", False) is True
    assert getattr(_parser().parse_args(["run", "-v"]), "verbose", False) is True


def test_missing_options_leave_no_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    args = _parser().parse_args(["run"])
    assert not hasattr(args, "source")
    assert not hasattr(args, "output")
    assert getattr(args, "force", False) is False


def test_resolve_config_applies_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = Config(source_export=Path("/default/source"), output_dir=None)
    monkeypatch.setattr(cli, "load_config", lambda: base)
    args = _parser().parse_args(["run", "-s", str(tmp_path / "in"), "-o", str(tmp_path / "out")])
    config = cli._resolve_config(args)
    assert config.source_export == (tmp_path / "in").resolve()
    assert config.output_dir == (tmp_path / "out").resolve()
    assert config.copy_dir == (tmp_path / "out").resolve()


def test_resolve_config_without_flags_returns_loaded_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = Config(source_export=Path("/default/source"))
    monkeypatch.setattr(cli, "load_config", lambda: base)
    args = _parser().parse_args(["organize"])
    assert cli._resolve_config(args) is base


def test_invalid_source_errors_before_copying() -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["copy", "-s", "/nonexistent/does-not-exist"])
    assert excinfo.value.code == 2
