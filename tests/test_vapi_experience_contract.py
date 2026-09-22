import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VAPI = ROOT / "config" / "vapi"


class VapiExperienceContractTests(unittest.TestCase):
    def test_tool_preserves_exact_experience_instead_of_bucketing(self):
        tool = json.loads((VAPI / "tool.logApplicantInfo.desired.json").read_text(encoding="utf-8"))
        experience = tool["function"]["parameters"]["properties"]["experience"]

        self.assertNotIn("enum", experience)
        self.assertIn("exact", experience["description"].lower())
        self.assertIn("5+ years", experience["description"])

    def test_assistant_prompts_forbid_experience_bucketing(self):
        for filename in ("new-lead.md", "existing-lead.md"):
            prompt = (VAPI / "prompts" / filename).read_text(encoding="utf-8")
            self.assertNotIn("Map their answer to one of", prompt)
            self.assertIn("Never bucket", prompt)
            self.assertIn("5+ years", prompt)

    def test_post_call_structured_data_preserves_experience_text(self):
        desired = json.loads((VAPI / "desired.json").read_text(encoding="utf-8"))
        experience = desired["shared"]["analysisPlan"]["structuredDataPlan"]["schema"]["properties"]["experience"]

        self.assertNotIn("enum", experience)
        self.assertIn("exact", experience["description"].lower())


if __name__ == "__main__":
    unittest.main()
