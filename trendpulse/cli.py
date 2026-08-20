from __future__ import annotations

import argparse
import logging
import sys


def _add_common(parser: argparse.ArgumentParser, *, suppress: bool) -> None:
    """--config/--verbose work both before AND after the subcommand
    (`trendpulse --config x run-daily` and `trendpulse run-daily --config x`).
    Subcommand copies use SUPPRESS defaults so an omitted flag never
    overwrites a value given before the subcommand."""
    default = argparse.SUPPRESS if suppress else None
    parser.add_argument("--config", default=default,
                        help="Path to config.yaml (default: config.yaml, then config.example.yaml)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        default=argparse.SUPPRESS if suppress else False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trendpulse",
        description="Trend spotting for SEO / AEO / GEO teams.",
    )
    _add_common(parser, suppress=False)
    sub = parser.add_subparsers(dest="command", required=True)

    commands = {
        "ingest": "Pull today's data from all enabled sources",
        "import": "Import offline GSC/GA4 dumps from data_imports/",
        "train": "Retrain the trend models on all collected history",
        "report": "Regenerate weekly/monthly/quarterly focus reports",
        "dashboard": "Re-render the HTML dashboard from existing data (no ingest/train)",
        "notify": "Send breakout alerts + briefing to Slack/Teams webhooks",
        "run-daily": "import + ingest + train + report + notify (the scheduled daily job)",
        "pack": "Compress the DB to data/trendpulse.db.gz — the snapshot git commits",
    }
    for name, help_text in commands.items():
        _add_common(sub.add_parser(name, help=help_text), suppress=True)

    demo = sub.add_parser("demo", help="Offline end-to-end run on synthetic data")
    _add_common(demo, suppress=True)
    demo.add_argument("--days", type=int, default=150,
                      help="Days of synthetic history to generate (default: 150)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    from trendpulse.config import load_config
    from trendpulse import pipeline

    cfg = load_config(args.config)

    if args.command == "ingest":
        obs, discs = pipeline.run_ingest(cfg)
        print(f"Ingested {obs} observations and {discs} discoveries.")
    elif args.command == "import":
        results = pipeline.run_import(cfg)
        print("Imported: " + ", ".join(f"{k}={v} observations" for k, v in results.items()))
    elif args.command == "train":
        models = pipeline.run_train(cfg)
        active = ", ".join(models) if models else "none (need more history)"
        print(f"Models trained: {active}")
    elif args.command == "report":
        print(f"Report written to {pipeline.run_report(cfg)}")
    elif args.command == "dashboard":
        print(f"Dashboard written to {pipeline.run_dashboard(cfg)}")
    elif args.command == "notify":
        sent = pipeline.run_notify(cfg)
        print("Alert sent." if sent else "Nothing sent (no webhooks or nothing to alert).")
    elif args.command == "run-daily":
        print(f"Report written to {pipeline.run_daily(cfg)}")
    elif args.command == "pack":
        from trendpulse.config import db_path
        from trendpulse.storage import pack_db
        print(f"Compressed snapshot written to {pack_db(db_path(cfg))}")
    elif args.command == "demo":
        path = pipeline.run_demo(cfg, days=args.days)
        print(f"Demo report written to {path}")
    else:  # pragma: no cover
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
