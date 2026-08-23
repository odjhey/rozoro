#!/usr/bin/env python3
"""Run the Rozoro monitor in the foreground."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.rozoro_monitor.server import AlreadyRunningError, MonitorServer


async def run(home: str | None) -> int:
    server = MonitorServer(home)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    try:
        await server.start()
        await stop.wait()
        return 0
    finally:
        await server.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="foreground Rozoro event monitor")
    parser.add_argument("--home", help="override ROZORO_HOME")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.home))
    except AlreadyRunningError as exc:
        print(f"rozorod: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
