from __future__ import annotations

import argparse
import logging
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trendpulse",
        description="Trend spotting for SEO / AEO / GEO teams.",
    )
    parser.add_argument("--config", default=None,
                        help="Path to config.yaml (default: config.yaml, then config.example.yaml)")
    parser.add_argument("--verbose", "-v", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest", help="Pull today's data from all enabled sources")
    sub.add_parser("train", help="Retrain the trend models on all collected history")
    sub.add_parser("report", help="Regenerate weekly/monthly/quarterly focus reports")
    sub.add_parser("run-daily", help="ingest + train + report (the scheduled daily job)")
    demo = sub.add_parser("demo", help="Offline end-to-end run on synthetic data")
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
    elif args.command == "train":
        models = pipeline.run_train(cfg)
        active = ", ".join(models) if models else "none (need more history)"
        print(f"Models trained: {active}")
    elif args.command == "report":
        print(f"Report written to {pipeline.run_report(cfg)}")
    elif args.command == "run-daily":
        print(f"Report written to {pipeline.run_daily(cfg)}")
    elif args.command == "demo":
        path = pipeline.run_demo(cfg, days=args.days)
        print(f"Demo report written to {path}")
    else:  # pragma: no cover
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
