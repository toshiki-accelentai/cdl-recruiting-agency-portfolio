import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITE_DIR = ROOT / "config" / "n8n" / "production" / "modular"
FILES = {
    "routing": "cdl-01-assistant-routing.json",
    "intake": "cdl-02-applicant-intake.json",
    "booking": "cdl-03-calendar-booking.json",
    "post_call": "cdl-04-post-call-report.json",
}


class ModularWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = {
            key: json.loads((SUITE_DIR / filename).read_text(encoding="utf-8"))
            for key, filename in FILES.items()
        }

    def test_suite_has_four_single_responsibility_workflows(self):
        self.assertEqual(set(self.workflows), {"routing", "intake", "booking", "post_call"})
        for workflow in self.workflows.values():
            self.assertLessEqual(len(workflow["nodes"]), 18, workflow["name"])

    def test_public_webhooks_are_isolated(self):
        paths = {}
        for key, workflow in self.workflows.items():
            paths[key] = {
                node["parameters"]["path"]
                for node in workflow["nodes"]
                if node["type"] == "n8n-nodes-base.webhook"
            }
        self.assertEqual(paths["routing"], {"cdl/assistant-request"})
        self.assertEqual(paths["intake"], {"cdl/log-applicant"})
        self.assertEqual(paths["post_call"], {"cdl/post-call"})
        self.assertEqual(paths["booking"], set())

    def test_booking_is_an_internal_subworkflow(self):
        booking_types = {node["type"] for node in self.workflows["booking"]["nodes"]}
        self.assertIn("n8n-nodes-base.executeWorkflowTrigger", booking_types)
        intake_nodes = {node["name"]: node for node in self.workflows["intake"]["nodes"]}
        execute = intake_nodes["Execute Calendar Booking"]
        self.assertEqual(execute["type"], "n8n-nodes-base.executeWorkflow")
        self.assertTrue(execute["parameters"]["options"]["waitForSubWorkflow"])

    def test_intake_restores_candidate_context_before_booking(self):
        intake = self.workflows["intake"]
        nodes = {node["name"]: node for node in intake["nodes"]}
        prepare = nodes["Prepare Booking Input"]
        self.assertIn("Resolve Candidate Result", prepare["parameters"]["jsCode"])
        self.assertIn("record?.code !== 'SUCCESS'", prepare["parameters"]["jsCode"])
        self.assertEqual(
            intake["connections"]["Add Intake Note"]["main"][0][0]["node"],
            "Prepare Booking Input",
        )
        self.assertEqual(
            intake["connections"]["Prepare Booking Input"]["main"][0][0]["node"],
            "Execute Calendar Booking",
        )

    def test_calendar_nodes_exist_only_in_booking(self):
        for key, workflow in self.workflows.items():
            google_nodes = [
                node for node in workflow["nodes"]
                if "googleapis.com/calendar" in str(node.get("parameters", {}).get("url", ""))
            ]
            self.assertEqual(len(google_nodes), 5 if key == "booking" else 0, key)

    def test_booking_uses_slot_lock_and_verifies_event_owner(self):
        booking = {node["name"]: node for node in self.workflows["booking"]["nodes"]}
        validate_code = booking["Validate Callback"]["parameters"]["jsCode"]
        booked_code = booking["Build Booked Result"]["parameters"]["jsCode"]
        self.assertIn("slotSeconds", validate_code)
        self.assertIn("toString(32)", validate_code)
        self.assertIn("extendedProperties?.private?.vapiCallId", booked_code)
        self.assertIn("slot_race_lost", booked_code)
        restore = booking["Restore Cancelled Slot"]
        self.assertEqual(restore["parameters"]["method"], "PUT")
        headers = restore["parameters"]["headerParameters"]["parameters"]
        self.assertEqual(headers[0]["name"], "If-Match")
        self.assertIn("etag", headers[0]["value"])

    def test_zoho_candidate_write_stays_in_intake(self):
        intake_names = {node["name"] for node in self.workflows["intake"]["nodes"]}
        self.assertIn("Write Candidate", intake_names)
        for key in ("routing", "booking", "post_call"):
            self.assertNotIn("Write Candidate", {n["name"] for n in self.workflows[key]["nodes"]})

    def test_generated_note_code_keeps_javascript_newline_escapes(self):
        intake = {node["name"]: node for node in self.workflows["intake"]["nodes"]}
        post_call = {node["name"]: node for node in self.workflows["post_call"]["nodes"]}
        self.assertIn("].join('\\n');", intake["Resolve Candidate Result"]["parameters"]["jsCode"])
        self.assertIn("].filter(Boolean).join('\\n\\n')", post_call["Build Post Call Note"]["parameters"]["jsCode"])

    def test_every_emitted_code_node_has_valid_javascript_syntax(self):
        for workflow in self.workflows.values():
            for node in workflow["nodes"]:
                if node["type"] != "n8n-nodes-base.code":
                    continue
                result = subprocess.run(
                    ["node", "-e", "new Function(process.argv[1])", node["parameters"]["jsCode"]],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, f"{workflow['name']} / {node['name']}: {result.stderr}")

    def test_every_workflow_has_execution_retention_settings(self):
        for workflow in self.workflows.values():
            settings = workflow["settings"]
            self.assertEqual(settings["saveDataErrorExecution"], "all")
            self.assertEqual(settings["saveDataSuccessExecution"], "none")
            self.assertFalse(settings["saveExecutionProgress"])
            self.assertEqual(settings["timezone"], "America/Vancouver")

    def test_async_zoho_writes_fail_the_execution_when_persistence_fails(self):
        intake = {node["name"]: node for node in self.workflows["intake"]["nodes"]}
        post_call = {node["name"]: node for node in self.workflows["post_call"]["nodes"]}
        self.assertIn("Verify Booking Note", intake)
        self.assertIn("throw new Error", intake["Verify Booking Note"]["parameters"]["jsCode"])
        self.assertIn("Verify Post-Call Note", post_call)
        self.assertIn("throw new Error", post_call["Verify Post-Call Note"]["parameters"]["jsCode"])

    def test_booking_response_carries_candidate_id_into_post_call_artifact(self):
        intake = {node["name"]: node for node in self.workflows["intake"]["nodes"]}
        response = intake["Respond Booking Result"]["parameters"]["responseBody"]
        self.assertIn("candidateId:$json.candidateId", response)

    def test_post_call_prefers_candidate_id_from_tool_result(self):
        post_call = {node["name"]: node for node in self.workflows["post_call"]["nodes"]}
        normalize = post_call["Normalize Post Call"]["parameters"]["jsCode"]
        lookup = post_call["Find Candidate for Post Call"]["parameters"]
        lookup_url = lookup["url"]
        self.assertIn("tool_call_result", normalize)
        self.assertIn("candidateId", normalize)
        self.assertIn("$json.candidateId", lookup_url)
        self.assertIn("encodeURIComponent", lookup_url)
        self.assertFalse(lookup.get("sendQuery", False))

    def test_post_call_note_exposes_readiness_postcode_and_cost(self):
        post_call = {node["name"]: node for node in self.workflows["post_call"]["nodes"]}
        normalize = post_call["Normalize Post Call"]["parameters"]["jsCode"]
        build = post_call["Build Post Call Note"]["parameters"]["jsCode"]

        self.assertIn("structuredData", normalize)
        self.assertIn("costBreakdown", normalize)
        self.assertIn("Readiness:", build)
        self.assertIn("Postcode analysis:", build)
        self.assertIn("Total cost: $", build)
        self.assertIn("AI Call Summary & Full Transcript", build)

    def test_code_node_references_exist_in_each_workflow(self):
        import re

        for workflow in self.workflows.values():
            names = {node["name"] for node in workflow["nodes"]}
            for node in workflow["nodes"]:
                code_text = node.get("parameters", {}).get("jsCode", "")
                for referenced in re.findall(r"\$\(['\"]([^'\"]+)['\"]\)", code_text):
                    self.assertIn(referenced, names, f"{workflow['name']} / {node['name']}")

    def test_suite_contains_no_forbidden_dependencies_or_secrets(self):
        serialized = json.dumps(self.workflows).lower()
        for forbidden in ("airtable", "gmail", "langchain", "openai", "client_secret", "refresh_token"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
