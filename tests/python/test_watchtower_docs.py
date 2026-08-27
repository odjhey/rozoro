import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text()
FACTS = (ROOT / "docs/watchtower-shared-facts.md").read_text()


class WatchtowerDocumentationTests(unittest.TestCase):
    def test_attribution_table_has_all_six_semantic_rows(self):
        rows = {}
        for line in README.splitlines():
            if line.startswith("| Pi ") or line.startswith("| Claude "):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                rows[cells[0]] = cells[1:]
        self.assertEqual(rows, {
            "Pi unnamed, unpreset": ["no", "no", "yes", "no preset attribution"],
            "Pi named, unpreset": ["yes", "no", "yes", "no preset attribution"],
            "Pi preset (default or explicit mission)": ["yes (preset default or override)", "yes", "yes", "yes, from preset"],
            "Claude unnamed, unpreset": ["no", "no", "no", "no preset attribution"],
            "Claude named, unpreset": ["yes", "no", "no", "no preset attribution"],
            "Claude preset": ["yes (preset default or override)", "yes", "no", "yes, from preset"],
        })

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
