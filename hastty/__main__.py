"""CLI entry point: `hastty` or `python -m hastty`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .app import HasttyApp
from .config import DEFAULT_CONFIG_PATH, load_config, write_example_config


def run() -> None:
    parser = argparse.ArgumentParser(prog="hastty", description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"Path to the config file (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Generate an example config file and exit.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging to hastty.log")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(filename="hastty.log", level=logging.DEBUG)

    if args.init_config:
        path = write_example_config(args.config)
        print(f"Example config created: {path}")
        print("Edit this file (or set HA_URL / HA_TOKEN) then run `hastty` again.")
        return

    try:
        config = load_config(args.config)
    except RuntimeError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        print("\nTip: run `hastty --init-config` to generate a starter config file.", file=sys.stderr)
        sys.exit(1)

    app = HasttyApp(config)
    app.run()


if __name__ == "__main__":
    run()
