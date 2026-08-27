import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text()
FACTS = (ROOT / "docs/watchtower-shared-facts.md").read_text()


def markdown_table(text: str, required_header: tuple[str, ...]) -> list[tuple[str, ...]]:
    """Return one exact Markdown table, rejecting moved/extra/short rows."""
    lines = text.splitlines()
    header = "| " + " | ".join(required_header) + " |"
    indexes = [i for i, line in enumerate(lines) if line == header]
    if len(indexes) != 1:
        raise AssertionError(f"expected exactly one attribution table, found {len(indexes)}")
    i = indexes[0]
    separator = tuple(cell.strip() for cell in lines[i + 1].strip("|").split("|"))
    if len(separator) != len(required_header) or any(not re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
        raise AssertionError("invalid attribution table separator")
    rows = []
    for line in lines[i + 2:]:
        if not line.startswith("|"):
            break
        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
        if len(cells) != len(required_header):
            raise AssertionError("invalid attribution table row width")
        rows.append(cells)
    return rows


class WatchtowerDocumentationTests(unittest.TestCase):
    def test_attribution_table_has_all_six_semantic_rows(self):
        parsed = markdown_table(README, ("Harness / launch", "name", "preset fields", "five-field Pi policy tuple", "model/effort attribution"))
        rows = {row[0]: list(row[1:]) for row in parsed}
        self.assertEqual(len(rows), len(parsed), "duplicate attribution ownership row")
        self.assertEqual(rows, {
            "Pi unnamed, unpreset": ["no", "no", "yes", "no preset attribution"],
            "Pi named, unpreset": ["yes", "no", "yes", "no preset attribution"],
            "Pi preset (default or explicit mission)": ["yes (preset default or override)", "yes", "yes", "yes, from preset"],
            "Claude unnamed, unpreset": ["no", "no", "no", "no preset attribution"],
            "Claude named, unpreset": ["yes", "no", "no", "no preset attribution"],
            "Claude preset": ["yes (preset default or override)", "yes", "no", "yes, from preset"],
        })

    def test_shared_facts_has_exact_positive_attribution_claims(self):
        # This is deliberately an exact positive sentence, not a flattened
        # substring search: negation, reassignment, missing/extra claims, or a
        # claim moved to another section all fail.
        section = FACTS.split("## Shared attribution\n", 1)[1].split("\n## ", 1)[0]
        paragraph = " ".join(section.split("- Every Pi launch records", 1)[1].split("- `watchtower-policy-snapshot`", 1)[0].split())
        expected = (
            "the complete five-field policy tuple. Every preset launch records preset name, operator-managed version, and exact preset-byte SHA-256. "
            "A named-unpreset launch records only its name plus harness-applicable attribution. Pi unnamed/unpreset and named/unpreset have the policy tuple but no preset/model attribution; "
            "Pi presets have all three. Claude unnamed/unpreset has none, Claude named/unpreset has only a name, and Claude presets have name/preset/model attribution but never the Pi tuple. "
            "`target.json` is current attribution; `registrations.jsonl` is history. Schema-1 history may retain an opaque legacy top-level `policy_sha256` without mission components; "
            "it is compatibility data, not current non-Pi policy attribution. New tuple ingress is accepted only for Pi."
        )
        self.assertEqual(paragraph, expected)

    def test_home_and_clearing_prose_is_semantically_complete(self):
        for text in (README, FACTS):
            prose = " ".join(text.split())
            self.assertRegex(prose, r"ROZORO_HOME.*?(?:else|>).*?(?:legacy.*?)?RZR_HOME.*?(?:else|>).*?(?:HOME/)?\.rozoro")
            self.assertRegex(prose, r"one (?:shared )?namespace")
        self.assertIn("complete five-field Pi policy tuple", README)
        self.assertIn("named-unpreset launch records only its name", FACTS)
        self.assertIn("Claude presets have name/preset/model attribution but never the Pi tuple", FACTS)


if __name__ == "__main__":
    unittest.main()
