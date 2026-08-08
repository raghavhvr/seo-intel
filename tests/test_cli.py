import pytest

from trendpulse.cli import build_parser


@pytest.mark.parametrize("argv", [
    ["run-daily", "--config", "config.yaml"],   # flag after subcommand (CI style)
    ["--config", "config.yaml", "run-daily"],   # flag before subcommand
])
def test_config_accepted_in_both_positions(argv):
    args = build_parser().parse_args(argv)
    assert args.command == "run-daily"
    assert args.config == "config.yaml"


def test_defaults_without_flags():
    args = build_parser().parse_args(["ingest"])
    assert args.config is None
    assert args.verbose is False


def test_verbose_after_subcommand():
    args = build_parser().parse_args(["report", "-v"])
    assert args.verbose is True


def test_demo_keeps_days_flag():
    args = build_parser().parse_args(["demo", "--days", "30", "--config", "x.yaml"])
    assert args.days == 30 and args.config == "x.yaml"
