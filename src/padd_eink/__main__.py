#!/usr/bin/env python3
# -*- coding:utf-8 -*-
import sys
import os
import logging
import argparse
import platform
import importlib.metadata

# --- Library Imports ---
from dotenv import load_dotenv
from pihole6api import PiHole6Client
from richcolorlog import setup_logging

from .tui import PADD_TUI
from .eink_display import run_eink_display

# --- Configuration ---
# Load environment variables from .env file in the project's root directory
project_dir = os.path.join(os.path.dirname(__file__), "..", "..")
load_dotenv(dotenv_path=os.path.join(project_dir, ".env"))

PIHOLE_IP = os.getenv("PIHOLE_IP")
API_TOKEN = os.getenv("API_TOKEN")

# --- Logging Setup ---
logger = None

# Display Configuration
SPLASH_SCREEN_DURATION_SECONDS = 10
SCREEN_AUTO_ROTATE_INTERVAL_SECONDS = 20
INFO_REFRESH_INTERVAL_SECONDS = 60 * 2


# Get the version of this script from the pyproject.toml
try:
    __version__ = importlib.metadata.version("padd-eink")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0-dev"


def create_pihole_client(pihole_ip, api_token):
    """Attempts to create and return a PiHole6Client instance."""
    logger.info(f"Connecting to Pi-hole at {pihole_ip}")
    try:
        client = PiHole6Client(pihole_ip, api_token)
        logger.info("Successfully connected to Pi-hole.")
        return client
    except Exception as e:
        logger.error(f"Could not connect to Pi-hole: {e}")
        return None


def main():
    global logger

    parser = argparse.ArgumentParser(description="Run the PADD e-Ink display.")
    parser.add_argument(
        "-V", "--version", action="version", version=f"PADD-eink v{__version__}"
    )
    parser.add_argument(
        "-T",
        "--tui",
        action="store_true",
        default=False,
        help="Run in terminal UI mode instead of e-Ink display.",
    )
    parser.add_argument(
        "-l",
        "--level",
        type=str.upper,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level (default: INFO)",
    )
    parser.add_argument(
        "-f", "--logfile", type=str, default=None, help="Specify a file to write logs to"
    )
    parser.add_argument(
        "-s",
        "--secure",
        action="store_true",
        default=False,
        help="Connect to Pi-hole using HTTPS",
    )
    parser.add_argument(
        "-t",
        "--traceback",
        action="store_true",
        default=False,
        help="Force enable rich tracebacks",
    )
    args = parser.parse_args()

    logger = setup_logging(
        level=getattr(logging, args.level), logfile=args.logfile, rich_tracebacks=args.traceback
    )

    if not PIHOLE_IP or not API_TOKEN:
        logger.critical("PIHOLE_IP and/or API_TOKEN not found in .env file.")
        sys.exit(1)

    protocol = "https" if args.secure else "http"
    pihole_url = f"{protocol}://{PIHOLE_IP}/admin/"
    pihole_auth = f"{protocol}://{PIHOLE_IP}"

    pihole_client = create_pihole_client(pihole_auth, API_TOKEN)

    is_arm = platform.machine() in ["armv7l", "aarch64", "armv6l"]

    if args.tui or not is_arm:
        if not args.tui and not is_arm:
            logger.info("Not running on a recognized ARM platform, forcing TUI mode.")
        app = PADD_TUI(pihole_client=pihole_client, pihole_url=pihole_url, __version__=__version__)
        app.run()
    else:
        run_eink_display(
            pihole_client=pihole_client,
            pihole_url=pihole_url,
            pihole_auth=pihole_auth,
            api_token=API_TOKEN,
            pihole_client_creator=create_pihole_client,
            splash_duration=SPLASH_SCREEN_DURATION_SECONDS,
            rotate_interval=SCREEN_AUTO_ROTATE_INTERVAL_SECONDS,
        )


if __name__ == "__main__":
    main()


