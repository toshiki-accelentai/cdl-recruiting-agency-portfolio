import unittest

from scripts.deploy_vapi_tool import build_payload


class DeployVapiToolTests(unittest.TestCase):
    def test_preserves_live_server_url_by_default(self):
        desired = {"function": {"name": "logApplicantInfo"}, "server": {"url": "https://new.example/webhook"}}
        live = {"server": {"url": "https://live.example/webhook", "timeoutSeconds": 20}}
        payload = build_payload(live, desired, repoint_server=False)
        self.assertEqual(payload["server"]["url"], "https://live.example/webhook")

    def test_repoints_only_when_explicit(self):
        desired = {"function": {"name": "logApplicantInfo"}, "server": {"url": "https://new.example/webhook"}}
        live = {"server": {"url": "https://live.example/webhook"}}
        payload = build_payload(live, desired, repoint_server=True)
        self.assertEqual(payload["server"]["url"], "https://new.example/webhook")


if __name__ == "__main__":
    unittest.main()
