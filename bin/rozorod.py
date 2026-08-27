#!/usr/bin/env python3
"""Run the Rozoro monitor in the foreground."""
import sys

if sys.version_info < (3, 11):
    print(
        "rozorod: Python >=3.11 is required (Python 3.10 is not yet supported; "
        "EOL Python 3.9 is out of policy); install Homebrew Python with "
        "`brew install python` and ensure its python3 precedes older interpreters on PATH "
        f"(found {sys.version.split()[0]} at {sys.executable})",
        file=sys.stderr,
    )
    raise SystemExit(2)

import argparse
import asyncio
import os
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.rozoro_monitor.client import UnsafePathError
from lib.rozoro_monitor.server import AlreadyRunningError, MonitorServer


async def run(home: str | None) -> int:
    server = MonitorServer(home)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    try:
        await server.start()
        signal_wait = asyncio.create_task(stop.wait())
        request_wait = asyncio.create_task(server.shutdown_requested.wait())
        done, pending = await asyncio.wait(
            {signal_wait, request_wait}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return 0
    finally:
        await server.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="foreground Rozoro event monitor")
    parser.add_argument("--home", help="override ROZORO_HOME")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        return asyncio.run(run(args.home))
    except (AlreadyRunningError, UnsafePathError) as exc:
        print(f"rozorod: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
