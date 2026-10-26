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

    def test_intake_saves_to_database_api_on_a_side_branch(self):
        """A3: the raw VAPI body goes to the DB API without touching the Zoho/booking path."""
        intake = self.workflows["intake"]
        nodes = {n["name"]: n for n in intake["nodes"]}
        save = nodes["Save to Database API"]
        params = save["parameters"]
        self.assertEqual(save["type"], "n8n-nodes-base.httpRequest")
        self.assertEqual(params["method"], "POST")
        self.assertEqual(params["url"], "http://cdl-api:8000/calls")
        self.assertEqual(params["jsonBody"], "={{ JSON.stringify($json.body) }}")
        self.assertNotIn("credentials", save)  # private Docker network, no auth yet (B3)
        # A failing API must never break the live call, and retries are safe (API is idempotent).
        self.assertEqual(save["onError"], "continueRegularOutput")
        self.assertTrue(save["retryOnFail"])
        self.assertLessEqual(save["maxTries"] * params["options"]["timeout"], 10000)
        # Fan-out from the webhook; the new node has no outgoing edges, so it cannot
        # change what Normalize Intake receives.
        targets = [e["node"] for e in intake["connections"]["Applicant Intake Webhook"]["main"][0]]
        self.assertEqual(targets, ["Save to Database API", "Normalize Intake"])
        self.assertNotIn("Save to Database API", intake["connections"])
        # Normalize Intake still reads the webhook body from its own input.
        self.assertIn("$json.body?.message", nodes["Normalize Intake"]["parameters"]["jsCode"])

    def test_add_api_branch_patches_a_live_workflow_without_touching_other_nodes(self):
        """The live Intake was hand-edited, so A3 adds only the new node + edge to it."""
        import copy
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_modular_workflows import add_save_to_api_branch

        live = copy.deepcopy(self.workflows["intake"])
        live["nodes"] = [n for n in live["nodes"] if n["name"] != "Save to Database API"]
        live["connections"]["Applicant Intake Webhook"]["main"][0] = [
            e for e in live["connections"]["Applicant Intake Webhook"]["main"][0]
            if e["node"] != "Save to Database API"]
        for n in live["nodes"]:  # simulate a hand edit made in the n8n UI
            if n["name"] == "Normalize Intake":
                n["parameters"]["jsCode"] += "\n// hand edit"
        before = copy.deepcopy(live)

        patched = add_save_to_api_branch(live)
        self.assertEqual(live, before)  # input not mutated
        names = [n["name"] for n in patched["nodes"]]
        self.assertEqual(names.count("Save to Database API"), 1)
        old = {n["name"]: n for n in before["nodes"]}
        for n in patched["nodes"]:
            if n["name"] != "Save to Database API":
                self.assertEqual(n, old[n["name"]], n["name"])
        edges = [e["node"] for e in patched["connections"]["Applicant Intake Webhook"]["main"][0]]
        self.assertEqual(edges, ["Save to Database API", "Normalize Intake"])
        # idempotent: patching twice changes nothing more
        self.assertEqual(add_save_to_api_branch(patched), patched)

    def test_api_key_auth_patch_changes_only_the_save_node(self):
        """B3: the API wants an X-API-Key; n8n sends it from a Header Auth credential (not in the JSON)."""
        import copy
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_modular_workflows import add_api_key_auth

        live = copy.deepcopy(self.workflows["intake"])
        before = copy.deepcopy(live)
        patched = add_api_key_auth(live, "cred-123", "CDL API key")
        self.assertEqual(live, before)  # input not mutated

        old = {n["name"]: n for n in before["nodes"]}
        changed = [n["name"] for n in patched["nodes"] if n != old[n["name"]]]
        self.assertEqual(changed, ["Save to Database API"])
        node = next(n for n in patched["nodes"] if n["name"] == "Save to Database API")
        self.assertEqual(node["parameters"]["authentication"], "genericCredentialType")
        self.assertEqual(node["parameters"]["genericAuthType"], "httpHeaderAuth")
        self.assertEqual(node["credentials"], {"httpHeaderAuth": {"id": "cred-123", "name": "CDL API key"}})
        # everything else on the node (url, body, timeout, retry, onError) is kept
        for key, value in old["Save to Database API"]["parameters"].items():
            self.assertEqual(node["parameters"][key], value, key)
        self.assertEqual(patched["connections"], before["connections"])
        # the secret itself never appears in the workflow
        self.assertNotIn("X-API-Key", json.dumps(patched))
        # idempotent
        self.assertEqual(add_api_key_auth(patched, "cred-123", "CDL API key"), patched)

    def test_api_key_auth_patch_refuses_a_workflow_without_the_save_node(self):
        import copy
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_modular_workflows import add_api_key_auth

        wf = copy.deepcopy(self.workflows["intake"])
        wf["nodes"] = [n for n in wf["nodes"] if n["name"] != "Save to Database API"]
        with self.assertRaises(ValueError):
            add_api_key_auth(wf, "cred-123", "CDL API key")

    def test_database_first_patch_leaves_the_worker_as_the_only_zoho_writer(self):
        """B1 follow-up: n8n and the outbox worker both wrote Zoho and created 2 candidates."""
        import copy
        import re
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_modular_workflows import ZOHO_WRITER_NODES, make_database_first

        live = copy.deepcopy(self.workflows["intake"])
        for n in live["nodes"]:  # simulate a hand edit made in the n8n UI
            if n["name"] == "Normalize Intake":
                n["parameters"]["jsCode"] += "\n// hand edit"
        before = copy.deepcopy(live)

        patched = make_database_first(live)
        self.assertEqual(live, before)  # input not mutated
        names = {n["name"] for n in patched["nodes"]}
        self.assertEqual(names, {n["name"] for n in before["nodes"]} - ZOHO_WRITER_NODES)
        for n in patched["nodes"]:  # no Zoho call left in n8n's intake
            self.assertNotIn("recruit.zoho.com", str(n["parameters"]), n["name"])

        # Only the two nodes that read the removed candidate nodes may change; hand edits survive.
        old = {n["name"]: n for n in before["nodes"]}
        changed = {n["name"] for n in patched["nodes"] if n != old[n["name"]]}
        self.assertEqual(changed, {"Prepare Booking Input", "Normalize Booking Outcome"})

        # No dangling edges, and the happy path is: valid -> book -> answer the caller.
        conns = patched["connections"]
        for src, c in conns.items():
            self.assertIn(src, names)
            for output in c["main"]:
                for edge in output:
                    self.assertIn(edge["node"], names, f"{src} -> {edge['node']}")
        self.assertEqual([e["node"] for e in conns["Intake Valid?"]["main"][0]], ["Prepare Booking Input"])
        self.assertEqual([e["node"] for e in conns["Intake Valid?"]["main"][1]], ["Respond Invalid Intake"])
        chain = ["Prepare Booking Input", "Execute Calendar Booking",
                 "Normalize Booking Outcome", "Respond Booking Result"]
        for src, dst in zip(chain, chain[1:]):
            self.assertEqual([e["node"] for e in conns[src]["main"][0]], [dst])
        self.assertNotIn("Respond Booking Result", conns)  # nothing runs after the caller is answered
        targets = [e["node"] for e in conns["Applicant Intake Webhook"]["main"][0]]
        self.assertEqual(targets, ["Save to Database API", "Normalize Intake"])

        # No code node may still read a node that was removed.
        for n in patched["nodes"]:
            code = n["parameters"].get("jsCode", "")
            for ref in re.findall(r"\$\('([^']+)'\)", code):
                self.assertIn(ref, names, f"{n['name']} reads removed node {ref}")
        prepare = {n["name"]: n for n in patched["nodes"]}["Prepare Booking Input"]["parameters"]["jsCode"]
        self.assertIn("$('Normalize Intake')", prepare)
        self.assertIn("candidateId: ''", prepare)  # the candidate may not exist yet: worker creates it
        # the "answer the caller" node still reports the call as saved and gives the booking result
        respond = {n["name"]: n for n in patched["nodes"]}["Respond Booking Result"]["parameters"]
        self.assertIn("saved:true", respond["responseBody"])

        self.assertEqual(make_database_first(patched), patched)  # idempotent

    def test_caller_hears_saved_only_after_the_database_save_worked(self):
        """Gap found in B1: the lead could be lost while the AI told the caller 'saved'."""
        import copy
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_modular_workflows import make_database_first, require_database_save

        base = make_database_first(copy.deepcopy(self.workflows["intake"]))
        before = copy.deepcopy(base)
        patched = require_database_save(base)
        self.assertEqual(base, before)  # input not mutated

        old = {n["name"]: n for n in before["nodes"]}
        new = {n["name"]: n for n in patched["nodes"]}
        self.assertEqual(set(new) - set(old), {"Saved to Database?", "Respond Save Failure"})
        for name, n in old.items():  # nothing else changes, hand edits survive
            self.assertEqual(new[name], n, name)

        conns = patched["connections"]
        out = lambda src, i: [e["node"] for e in conns[src]["main"][i]]  # noqa: E731
        self.assertEqual(out("Intake Valid?", 0), ["Saved to Database?"])
        self.assertEqual(out("Intake Valid?", 1), ["Respond Invalid Intake"])
        self.assertEqual(out("Saved to Database?", 0), ["Prepare Booking Input"])
        self.assertEqual(out("Saved to Database?", 1), ["Respond Save Failure"])
        self.assertNotIn("Respond Save Failure", conns)
        for src, c in conns.items():  # no dangling edges
            self.assertIn(src, new)
            for output in c["main"]:
                for edge in output:
                    self.assertIn(edge["node"], new, f"{src} -> {edge['node']}")
        # The check reads the save result, so the save must finish first: it is the first fan-out edge.
        self.assertEqual(out("Applicant Intake Webhook", 0)[0], "Save to Database API")

        # The honest answer for a lead we could not store.
        failure = new["Respond Save Failure"]["parameters"]["responseBody"]
        for text in ("manual_followup", "saved:false", "booked:false", "$json.toolCallId", "$json.callId"):
            self.assertIn(text, failure)
        self.assertEqual(new["Respond Save Failure"]["parameters"]["options"]["responseCode"], 200)

        # Run the real condition in Node: saved when the API returned a call id, not saved otherwise.
        condition = new["Saved to Database?"]["parameters"]["conditions"]["conditions"][0]["leftValue"]
        self.assertTrue(condition.startswith("={{") and condition.endswith("}}"))
        expression = condition[3:-2].strip()
        script = ("const cases = %s; const out = cases.map(c => { const $ = () => ({first: () => ({json: c})}); "
                  "return (%s); }); console.log(JSON.stringify(out));" % (
                      json.dumps([{"call_id": 7, "applicant_id": 7, "duplicate": False},
                                  {"call_id": 7, "duplicate": True},
                                  {"error": {"message": "connect ECONNREFUSED"}},
                                  {"error": {"message": "timeout"}, "statusCode": 500},
                                  {}]), expression))
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [True, True, False, False, False])

        self.assertEqual(require_database_save(patched), patched)  # idempotent

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

    def test_intake_uses_phone_fallback_and_location_validation(self):
        intake = {n["name"]: n for n in self.workflows["intake"]["nodes"]}
        code = intake["Normalize Intake"]["parameters"]["jsCode"]
        self.assertIn("pickPhone(args.phoneNumber, message.call?.customer?.number)", code)
        self.assertIn("errors.push(...validateLocation(location))", code)
        self.assertNotIn("normalizePhone(args.phoneNumber ??", code)
        # The live node also rejects bad callback times; the builder must not drop that.
        self.assertIn("validateCallback(args.preferredCallbackTime)", code)
        self.assertIn("callbackStartUtc: callback.startUtc ?? null", code)

    def test_routing_reads_the_caller_number_from_either_place_even_when_one_is_empty(self):
        routing = {n["name"]: n for n in self.workflows["routing"]["nodes"]}
        code = routing["Normalize Route Request"]["parameters"]["jsCode"]
        self.assertIn("pickPhone(message.call?.customer?.number, message.customer?.number)", code)
        self.assertNotIn("normalizePhone(message.call?.customer?.number ??", code)

    def test_routing_asks_the_database_first_and_zoho_only_when_the_database_does_not_know(self):
        wf = self.workflows["routing"]
        nodes = {n["name"]: n for n in wf["nodes"]}
        edges = {src: [[t["node"] for t in out] for out in v["main"]] for src, v in wf["connections"].items()}
        self.assertEqual(edges["Normalize Route Request"], [["Find Applicant in Database"]])
        self.assertEqual(edges["Find Applicant in Database"], [["Found in Database?"]])
        self.assertEqual(edges["Found in Database?"], [["Build Assistant Response"], ["Find Candidate for Routing"]])
        self.assertEqual(edges["Find Candidate for Routing"], [["Build Assistant Response"]])
        lookup = nodes["Find Applicant in Database"]
        self.assertEqual(lookup["parameters"]["url"], "http://cdl-api:8000/applicants/lookup")
        self.assertEqual(lookup["parameters"]["genericAuthType"], "httpHeaderAuth")
        self.assertEqual(lookup.get("onError"), "continueRegularOutput")  # API down -> still route via Zoho
        self.assertTrue(lookup.get("alwaysOutputData"))

    def test_routing_timeouts_fit_inside_vapis_7_5_second_limit(self):
        nodes = {n["name"]: n for n in self.workflows["routing"]["nodes"]}
        database = nodes["Find Applicant in Database"]["parameters"]["options"]["timeout"]
        zoho = nodes["Find Candidate for Routing"]["parameters"]["options"]["timeout"]
        self.assertEqual((database, zoho), (2000, 4000))
        self.assertFalse(nodes["Find Applicant in Database"].get("retryOnFail"))
        self.assertFalse(nodes["Find Candidate for Routing"].get("retryOnFail"))
        self.assertLess(database + zoho, 7500)

    def run_build_assistant_response(self, route, database, zoho):
        code = {n["name"]: n for n in self.workflows["routing"]["nodes"]}["Build Assistant Response"]["parameters"]["jsCode"]
        runner = (
            "const [code, route, db, zoho] = process.argv.slice(1).map((v, i) => i ? JSON.parse(v) : v);"
            "const outputs = {'Normalize Route Request': route, 'Find Applicant in Database': db};"
            "const $ = (name) => ({ first: () => ({ json: outputs[name] }) });"
            "console.log(JSON.stringify(new Function('$', '$json', code)($, zoho ?? db)[0].json));"
        )
        result = subprocess.run(["node", "-e", runner, code, json.dumps(route), json.dumps(database), json.dumps(zoho)],
                                capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_a_caller_found_in_the_database_is_existing_and_greeted_with_the_database_name(self):
        out = self.run_build_assistant_response(
            {"phone": "+12065550101", "valid": True}, {"found": True, "name": "Maria De La Cruz"}, None)
        self.assertEqual(out["routing"], "existing_database")
        self.assertEqual(out["assistantOverrides"]["variableValues"]["name"], "Maria De La Cruz")
        self.assertEqual(out["assistantId"], "542bae1c-51b5-4d83-a3fe-446836b4801d")

    def test_a_caller_found_in_the_database_hands_the_on_file_details_to_the_agent(self):
        on_file = {"city": "Dallas", "state": "TX", "zipCode": "75201", "experience": "5 years", "readiness": "within 7 days"}
        out = self.run_build_assistant_response(
            {"phone": "+12065550101", "valid": True}, {"found": True, "name": "Maria De La Cruz", **on_file}, None)
        values = out["assistantOverrides"]["variableValues"]
        self.assertEqual({k: values[k] for k in on_file}, on_file)

    def test_a_caller_only_in_zoho_has_no_on_file_details_so_the_agent_asks(self):
        out = self.run_build_assistant_response(
            {"phone": "+12065550101", "valid": True}, {"found": False, "name": ""},
            {"data": [{"id": "9", "First_Name": "Jo", "Last_Name": "Diaz"}]})
        values = out["assistantOverrides"]["variableValues"]
        for key in ("city", "state", "zipCode", "experience", "readiness"):
            self.assertEqual(values[key], "", key)

    def test_the_existing_lead_prompt_sends_the_details_on_file_to_the_save_tool(self):
        prompt = (ROOT / "config" / "vapi" / "prompts" / "existing-lead.md").read_text(encoding="utf-8")
        for key in ("city", "state", "zipCode", "experience", "readiness"):
            self.assertIn("{{ %s | default: \"NOT ON FILE\" }}" % key, prompt, key)
        self.assertIn("send the details on file", prompt)

    def test_a_caller_only_in_zoho_is_still_existing(self):
        out = self.run_build_assistant_response(
            {"phone": "+12065550101", "valid": True}, {"found": False, "name": ""},
            {"data": [{"id": "9", "First_Name": "Jo", "Last_Name": "Diaz"}]})
        self.assertEqual(out["routing"], "existing_candidate")
        self.assertEqual(out["assistantOverrides"]["variableValues"]["name"], "Jo Diaz")

    def test_a_caller_in_neither_place_or_when_both_lookups_fail_is_new(self):
        for database, zoho in (({"found": False, "name": ""}, {}), ({"error": "timeout"}, {"error": "timeout"})):
            out = self.run_build_assistant_response({"phone": "+12065550101", "valid": True}, database, zoho)
            self.assertEqual(out["routing"], "new_candidate")
            self.assertEqual(out["assistantId"], "6901a714-a6c5-45a2-9395-455e09e0051b")
            self.assertEqual(out["assistantOverrides"]["variableValues"]["name"], "")

    def test_booking_ends_at_the_two_result_nodes_without_a_pass_through_node(self):
        wf = self.workflows["booking"]
        names = {n["name"] for n in wf["nodes"]}
        self.assertNotIn("Return Booking Result", names)
        self.assertNotIn("Build Booked Result", wf["connections"])
        self.assertNotIn("Build Non-Booking Result", wf["connections"])
        # Kept on purpose: after a conditional (If-Match) restore loses a race, the read-back shows the
        # other caller owns the slot, so this caller hears "time taken" instead of "manual follow-up".
        self.assertIn("Confirm Restored Slot", names)

    def booked_result(self, context, event):
        code = {n["name"]: n for n in self.workflows["booking"]["nodes"]}["Build Booked Result"]["parameters"]["jsCode"]
        runner = ("const [code, ctx, ev] = process.argv.slice(1).map((v, i) => i ? JSON.parse(v) : v);"
                  "const $ = () => ({ first: () => ({ json: ctx }) });"
                  "console.log(JSON.stringify(new Function('$', '$json', code)($, ev)[0].json));")
        out = subprocess.run(["node", "-e", runner, code, json.dumps(context), json.dumps(event)],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_a_slot_someone_else_holds_is_slot_taken_not_outside_business_hours(self):
        ctx = {"eventId": "cdlslot1", "callId": "call-A", "bookingReason": "slot_unavailable"}
        theirs = {"id": "cdlslot1", "status": "confirmed", "extendedProperties": {"private": {"vapiCallId": "call-B"}}}
        mine = {"id": "cdlslot1", "status": "confirmed", "htmlLink": "h", "extendedProperties": {"private": {"vapiCallId": "call-A"}}}
        self.assertEqual(self.booked_result(ctx, theirs)["status"], "slot_taken")
        self.assertEqual(self.booked_result({**ctx, "bookingReason": "available"}, theirs)["status"], "slot_taken")
        self.assertEqual(self.booked_result(ctx, mine)["status"], "booked")  # a retry of the same call
        failed = self.booked_result({**ctx, "bookingReason": "available"}, {"error": {"message": "x"}})
        self.assertEqual(failed["status"], "manual_followup")

    def test_every_node_with_the_helpers_carries_the_current_helper_text(self):
        helpers = (ROOT / "workflow-src" / "cdl_helpers.js").read_text(encoding="utf-8")
        embedding = [
            (w["name"], n["name"]) for w in self.workflows.values() for n in w["nodes"]
            if "function classifyTemperature" in n.get("parameters", {}).get("jsCode", "")
        ]
        self.assertEqual(len(embedding), 4, embedding)
        for workflow in self.workflows.values():
            for node in workflow["nodes"]:
                js = node.get("parameters", {}).get("jsCode", "")
                if "function classifyTemperature" in js:
                    self.assertTrue(js.startswith(helpers), f"{workflow['name']} / {node['name']} has stale helpers")

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
