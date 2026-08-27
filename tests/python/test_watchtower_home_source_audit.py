"""Completeness audit for tracked ROZORO_HOME selectors.

This inventory is source evidence only.  It deliberately makes no claim that a
consumer's home-selection behaviour has been exercised.
"""

from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/watchtower-home-consumers.json"
DEFAULT_SELECTOR = re.compile(
    r"(?s)(?:ROZORO_HOME.{0,240}RZR_HOME|RZR_HOME.{0,240}ROZORO_HOME)"
    r".{0,240}(?:~/\.rozoro|HOME[^\n]{0,40}\.rozoro|homedir\(\)[^\n]{0,80}\.rozoro)"
)
SOURCE_SUFFIXES = {".py", ".sh", ".ts", ".js", ".bash"}


def tracked_sources() -> dict[str, str]:
    # CI's pinned test container intentionally has no git binary or .git mount.
    # A clean checkout makes these production roots the tracked-source surface;
    # restricting the roots also excludes docs and ignored local .claude copies.
    sources = {}
    for source_root in ("bin", "lib", "hooks", ".agents", ".pi"):
        for path in (ROOT / source_root).rglob("*"):
            name = path.relative_to(ROOT).as_posix()
            if not path.is_file() or (
                path.suffix not in SOURCE_SUFFIXES and source_root != "bin"
            ):
                continue
            try:
                sources[name] = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                pass
    return sources


def audit(inventory: dict, sources: dict[str, str]) -> list[str]:
    errors: list[str] = []
    sections = ("direct_default", "inherited_explicit_only", "excluded")
    memberships: dict[str, str] = {}
    for section in sections:
        for path, needles in inventory[section].items():
            if path in memberships:
                errors.append(f"{path}: classified twice")
            memberships[path] = section
            text = sources.get(path)
            if text is None:
                errors.append(f"{path}: fixture entry is not tracked source")
            elif any(needle not in text for needle in needles):
                errors.append(f"{path}: fixture selector has no source match")

    selectors = {path for path, text in sources.items() if DEFAULT_SELECTOR.search(text)}
    missing = selectors - set(inventory["direct_default"])
    for path in sorted(missing):
        errors.append(f"{path}: tracked default-home selector absent from direct_default")

    for path in inventory["inherited_explicit_only"]:
        if path in selectors:
            errors.append(f"{path}: direct selector mislabeled inherited/explicit-only")
    return errors


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class HomeSourceAuditTests(unittest.TestCase):
    def test_tracked_home_consumer_inventory_is_complete(self) -> None:
        self.assertEqual(audit(load_fixture(), tracked_sources()), [])


    def test_source_addition_mutant_is_rejected(self) -> None:
        sources = tracked_sources()
        sources["bin/rzr-new-home-tool.py"] = (
            'home = os.environ.get("ROZORO_HOME") or os.environ.get("RZR_HOME") '
            'or "~/.rozoro"\n'
        )
        assert any("rzr-new-home-tool.py: tracked default-home selector absent" in e
                   for e in audit(load_fixture(), sources))


    def test_fixture_removal_and_stale_mutants_are_rejected(self) -> None:
        inventory = load_fixture()
        removed = copy.deepcopy(inventory)
        del removed["direct_default"]["bin/rzr-monitor.py"]
        assert any("bin/rzr-monitor.py: tracked default-home selector absent" in e
                   for e in audit(removed, tracked_sources()))

        stale = copy.deepcopy(inventory)
        stale["direct_default"]["bin/removed-home-tool.py"] = ["ROZORO_HOME"]
        assert "bin/removed-home-tool.py: fixture entry is not tracked source" in audit(
            stale, tracked_sources()
        )


    def test_direct_as_inherited_mutant_is_rejected(self) -> None:
        inventory = load_fixture()
        needles = inventory["direct_default"].pop("bin/rzr-lib.sh")
        inventory["inherited_explicit_only"]["bin/rzr-lib.sh"] = needles
        assert "bin/rzr-lib.sh: direct selector mislabeled inherited/explicit-only" in audit(
            inventory, tracked_sources()
        )


    def test_codex_store_adapter_is_excluded_exactly(self) -> None:
        inventory = load_fixture()
        assert inventory["excluded"] == {"bin/rzr-codex-event-adapter.py": ["--store"]}
        assert "bin/rzr-codex-event-adapter.py" not in inventory["direct_default"]
        assert "bin/rzr-codex-event-adapter.py" not in inventory["inherited_explicit_only"]
