#!/usr/bin/env python3
"""CLI wrapper around the canonical Rozoro handoff parser."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.rozoro_monitor.handoff import parse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("handoff")
    parser.add_argument("--acked-v2")
    parser.add_argument("--acked-legacy")
    args = parser.parse_args()
    print(json.dumps(parse(args.handoff, args.acked_v2, args.acked_legacy),
                     sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
