import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "config" / "n8n" / "production" / "cdl-intake-production.json"


class ProductionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        cls.nodes = cls.workflow["nodes"]
        cls.by_name = {node["name"]: node for node in cls.nodes}

    def test_single_workflow_has_three_stable_entrypoints(self):
        webhooks = [n for n in self.nodes if n["type"] == "n8n-nodes-base.webhook"]
        self.assertEqual(
            {n["parameters"]["path"] for n in webhooks},
            {"cdl/assistant-request", "cdl/log-applicant", "cdl/post-call"},
        )

    def test_unnecessary_services_and_ai_are_removed(self):
        forbidden = ("airtable", "gmail", "langchain", "openai")
        node_types = "\n".join(n["type"].lower() for n in self.nodes)
        for value in forbidden:
            self.assertNotIn(value, node_types)

    def test_no_manual_oauth_token_exchange(self):
        serialized = json.dumps(self.workflow)
        self.assertNotIn("/oauth/v2/token", serialized)
        self.assertNotIn("client_secret", serialized.lower())
        self.assertNotIn("refresh_token", serialized.lower())

    def test_all_zoho_requests_use_saved_oauth_and_retries(self):
        zoho_nodes = [
            n for n in self.nodes
            if n["type"] == "n8n-nodes-base.httpRequest"
            and "recruit.zoho.com" in str(n["parameters"].get("url", ""))
        ]
        self.assertGreaterEqual(len(zoho_nodes), 5)
        for node in zoho_nodes:
            self.assertEqual(node["parameters"]["authentication"], "genericCredentialType")
            self.assertEqual(node["parameters"]["genericAuthType"], "oAuth2Api")
            self.assertIn("oAuth2Api", node["credentials"])
            self.assertTrue(node["retryOnFail"])
            self.assertGreaterEqual(node["maxTries"], 3)
            self.assertEqual(node["onError"], "continueRegularOutput")

    def test_calendar_checks_before_create(self):
        names = [n["name"] for n in self.nodes]
        self.assertIn("Check Calendar Availability", names)
        self.assertIn("Create Calendar Event", names)
        self.assertIn("Confirm Calendar Event", names)
        availability = self.by_name["Check Calendar Availability"]
        create = self.by_name["Create Calendar Event"]
        confirm = self.by_name["Confirm Calendar Event"]
        self.assertEqual(availability["type"], "n8n-nodes-base.httpRequest")
        self.assertEqual(availability["parameters"]["method"], "POST")
        self.assertEqual(availability["parameters"]["url"], "https://www.googleapis.com/calendar/v3/freeBusy")
        self.assertEqual(create["parameters"]["method"], "POST")
        self.assertIn("/events", create["parameters"]["url"])
        self.assertEqual(confirm["parameters"]["method"], "GET")
        self.assertIn("eventId", confirm["parameters"]["url"])

    def test_google_requests_use_saved_oauth(self):
        google_nodes = [
            n for n in self.nodes
            if n["type"] == "n8n-nodes-base.httpRequest"
            and "googleapis.com/calendar" in str(n["parameters"].get("url", ""))
        ]
        self.assertEqual(len(google_nodes), 5)
        for node in google_nodes:
            self.assertEqual(node["parameters"]["authentication"], "predefinedCredentialType")
            self.assertEqual(node["parameters"]["nodeCredentialType"], "googleCalendarOAuth2Api")
            self.assertIn("googleCalendarOAuth2Api", node["credentials"])
            self.assertNotEqual(
                node["credentials"]["googleCalendarOAuth2Api"]["id"],
                "1dIX8usZgX3ubw1F",
            )

    def test_external_nodes_have_bounded_retry_policy(self):
        external_types = {"n8n-nodes-base.httpRequest"}
        for node in self.nodes:
            if node["type"] in external_types:
                self.assertTrue(node.get("retryOnFail"), node["name"])
                self.assertLessEqual(node.get("maxTries", 99), 3, node["name"])
                self.assertLessEqual(node.get("waitBetweenTries", 99999), 2000, node["name"])

    def test_vapi_tool_always_has_response_branches(self):
        expected = {
            "Respond Invalid Intake",
            "Respond Candidate Failure",
            "Respond Booking Result",
        }
        self.assertTrue(expected.issubset(self.by_name))
        for name in expected:
            self.assertEqual(self.by_name[name]["type"], "n8n-nodes-base.respondToWebhook")

    def test_workflow_is_smaller_than_current_combined_system(self):
        self.assertLessEqual(len(self.nodes), 40)

    def test_no_embedded_secret_shapes(self):
        serialized = json.dumps(self.workflow)
        self.assertIsNone(re.search(r"1000\.[A-Za-z0-9]{10,}", serialized))
        self.assertIsNone(re.search(r"\b[0-9a-f]{32,}\b", serialized))


if __name__ == "__main__":
    unittest.main()
