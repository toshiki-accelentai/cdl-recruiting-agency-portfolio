import unittest

from scripts.deploy_n8n_suite import inject_booking_id


class DeployN8nSuiteTests(unittest.TestCase):
    def test_injects_booking_workflow_id_into_intake(self):
        intake = {
            "nodes": [{
                "name": "Execute Calendar Booking",
                "parameters": {"workflowId": {"value": "placeholder"}},
            }]
        }
        updated = inject_booking_id(intake, "booking-123")
        self.assertEqual(
            updated["nodes"][0]["parameters"]["workflowId"]["value"],
            "booking-123",
        )


if __name__ == "__main__":
    unittest.main()
