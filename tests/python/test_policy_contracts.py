import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "DONE", "NEEDS_IMPLEMENTATION", "NEEDS_TESTS", "NEEDS_REVIEW",
    "NEEDS_DECISION", "NEEDS_REPLAN", "NEEDS_INFRA_REPAIR",
    "NEEDS_GATE_REPAIR", "BLOCKED_EXTERNAL",
}
DOCS = {
    "mission": ROOT / "templates/missions/delivery.md",
    "dispatch": ROOT / "templates/watchtower-crew-dispatch-guidelines.md",
    "runbook": ROOT / "docs/runbooks/role-separated-delivery.md",
}
REPAIR_DOCS = {
    **DOCS,
    "budget": ROOT / ".agents/skills/attempt-budget/SKILL.md",
}


def text(path):
    return path.read_text(encoding="utf-8")


def table_statuses(value):
    return set(re.findall(r"^\| `([A-Z_]+)` \|", value, re.MULTILINE))



class PolicyContractsTest(unittest.TestCase):
    def test_closed_status_set_agrees(self):
        for name, path in DOCS.items():
            assert table_statuses(text(path)) == EXPECTED, name


    def test_only_replan_charges_replan_count(self):
        forbidden = re.compile(r"NEEDS_(?!REPLAN)[A-Z_]+.{0,100}increments `replan_count`", re.S)
        for path in REPAIR_DOCS.values():
            assert not forbidden.search(text(path)), path


    def test_repair_metadata_and_cap_agree(self):
        fields = ("repair_lineage_id", "implementation_lineage_id",
                  "infra_repair_count", "gate_repair_count", "repair_limit")
        for name, path in REPAIR_DOCS.items():
            value = text(path)
            assert all(field in value for field in fields), name
            assert "repair_limit: 3" in value, name
            assert "infra_repair_count + gate_repair_count <= 3" in value, name


    def test_ad_hoc_routing_precedence_and_execution_verification(self):
        paths = [ROOT / ".agents/skills/crew-model-selection/SKILL.md",
                 DOCS["dispatch"], DOCS["runbook"]]
        ordered = re.compile(r"operator[\s\S]{0,80}>[\s\S]{0,80}repository[\s\S]{0,80}>[\s\S]{0,80}durable[\s\S]{0,120}>[\s\S]{0,80}machine[\s\S]{0,80}>[\s\S]{0,80}preset", re.I)
        for path in paths:
            value = text(path)
            assert ordered.search(value), path
            assert "Immediately" in value and "verify" in value, path


    def test_shared_facts_requires_mission_opt_in(self):
        value = text(ROOT / "docs/watchtower-shared-facts.md")
        assert "only when that mission explicitly opts" in value
        assert "silent mission retains a closed role list" in value


    def test_adr_0014_is_approved_and_indexed(self):
        adr = text(ROOT / "docs/decisions/0014-delivery-failure-routing-and-ad-hoc-specialists.md")
        index = text(ROOT / "docs/decisions/README.md")
        assert "review: approved" in adr
        assert "ADR-0012" in adr and "ADR-0013" in adr
        assert "0014-delivery-failure-routing-and-ad-hoc-specialists.md" in index
        assert "ADR-0014" in index.split("ADR-0009", 1)[1]

if __name__ == "__main__":
    unittest.main()
