from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from xpost.config import load_settings, load_sources
from xpost.env import load_dotenv
from xpost.llm.chain import build_chain
from xpost.run import run_daily
from xpost.state import State


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xpost", description="Daily X post drafts for Discord")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="draft today's post and send it to Discord")
    run.add_argument("--config", type=Path, default=Path("config/bot.yaml"), help="path to bot.yaml")
    run.add_argument("--state", type=Path, default=Path("state/state.json"), help="path to the state json file")
    run.add_argument("--dry-run", action="store_true", help="print the draft instead of sending it; saves nothing")
    run.add_argument("--force", action="store_true", help="draft again even if today already has a draft")
    run.add_argument("--env-file", type=Path, default=Path(".env"), help="file with local secrets (default: .env)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv(args.env_file)

    settings = load_settings(args.config)
    webhook_url = os.environ.get(settings.webhook_env)
    if not args.dry_run and not webhook_url:
        print(
            f"error: {settings.webhook_env} is not set (add it to {args.env_file} or the environment)",
            file=sys.stderr,
        )
        return 2

    chain = build_chain(settings.providers, os.environ)
    if not chain.providers:
        logging.warning("no model provider has a key; a draft cannot be written")

    result = run_daily(
        settings,
        load_sources(Path(settings.sources_file)),
        State(args.state),
        chain,
        datetime.now(timezone.utc),
        webhook_url,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(result.message)
    return 1 if result.status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
