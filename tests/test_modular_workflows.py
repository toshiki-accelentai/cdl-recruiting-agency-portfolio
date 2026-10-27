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
            # 20: booking grew by the "replace previous callback" steps (2026-10-27); keep each workflow small.
            self.assertLessEqual(len(workflow["nodes"]), 20, workflow["name"])

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
            # 7 = availability, create, confirm, restore, confirm restore, find others, cancel replaced.
            self.assertEqual(len(google_nodes), 7 if key == "booking" else 0, key)

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
        self.assertNotIn("Finish Booking Result", wf["connections"])  # the end of the booked path
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

    # --- one upcoming callback per phone: a new booking replaces the caller's other upcoming callbacks ---------

    def booking_nodes(self):
        return {n["name"]: n for n in self.workflows["booking"]["nodes"]}

    def booking_edges(self):
        wf = self.workflows["booking"]
        return {src: [[t["node"] for t in out] for out in v["main"]] for src, v in wf["connections"].items()}

    def test_new_events_carry_the_caller_phone_so_their_other_callbacks_can_be_found(self):
        code = self.booking_nodes()["Build Calendar Event"]["parameters"]["jsCode"]
        self.assertIn("callerPhone: $json.phone", code)

    def test_only_a_confirmed_booking_looks_for_callbacks_to_replace(self):
        e = self.booking_edges()
        self.assertEqual(e["Build Booked Result"], [["Booked?"]])
        self.assertEqual(e["Booked?"], [["Find Other Upcoming Callbacks"], ["Finish Booking Result"]])
        self.assertEqual(e["Find Other Upcoming Callbacks"], [["Pick Callbacks to Replace"]])
        self.assertEqual(e["Pick Callbacks to Replace"], [["Anything to Replace?"]])
        self.assertEqual(e["Anything to Replace?"], [["Cancel Replaced Callback"], ["Finish Booking Result"]])
        self.assertEqual(e["Cancel Replaced Callback"], [["Finish Booking Result"]])
        self.assertNotIn("Finish Booking Result", e)  # the end of the booked path

    def test_the_replace_steps_are_quick_and_never_fail_the_booking(self):
        n = self.booking_nodes()
        find, cancel = n["Find Other Upcoming Callbacks"], n["Cancel Replaced Callback"]
        query = {q["name"]: q["value"] for q in find["parameters"]["queryParameters"]["parameters"]}
        self.assertEqual(query["privateExtendedProperty"], "=callerPhone={{ $json.phone }}")
        self.assertIn("timeMin", query)
        self.assertEqual(cancel["parameters"]["method"], "DELETE")
        for node in (find, cancel):
            self.assertEqual(node["parameters"]["options"]["timeout"], 5000)
            self.assertFalse(node.get("retryOnFail"))
            self.assertEqual(node.get("onError"), "continueRegularOutput")

    def run_booking_code(self, node, outputs, input_items):
        code = self.booking_nodes()[node]["parameters"]["jsCode"]
        runner = (
            "const [code, outputs, input] = process.argv.slice(1).map((v, i) => i ? JSON.parse(v) : v);"
            "const $ = (name) => { if (!(name in outputs)) throw new Error('not executed: ' + name);"
            "  return { first: () => ({ json: outputs[name][0] }), all: () => outputs[name].map(j => ({ json: j })) }; };"
            "const $input = { first: () => ({ json: input[0] }), all: () => input.map(j => ({ json: j })) };"
            "console.log(JSON.stringify(new Function('$', '$input', code)($, $input).map(i => i.json)));"
        )
        out = subprocess.run(["node", "-e", runner, code, json.dumps(outputs), json.dumps(input_items)],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    BOOKED = {"status": "booked", "booked": True, "calendarEventId": "cdlslotNEW", "phone": "+12065550101"}

    def test_only_the_callers_other_upcoming_events_are_picked(self):
        listing = {"items": [
            {"id": "cdlslotNEW", "status": "confirmed", "extendedProperties": {"private": {"callerPhone": "+12065550101"}}},
            {"id": "cdlslotOLD", "status": "confirmed", "extendedProperties": {"private": {"callerPhone": "+12065550101"}}},
            {"id": "cdlslotGONE", "status": "cancelled", "extendedProperties": {"private": {"callerPhone": "+12065550101"}}},
            {"id": "cdlslotOTHER", "status": "confirmed", "extendedProperties": {"private": {"callerPhone": "+19995550000"}}},
            {"id": "manual123", "status": "confirmed", "extendedProperties": {"private": {"callerPhone": "+12065550101"}}},
        ]}
        out = self.run_booking_code("Pick Callbacks to Replace", {"Build Booked Result": [self.BOOKED]}, [listing])
        self.assertEqual([o["cancelId"] for o in out], ["cdlslotOLD"])

    def test_nothing_to_replace_or_a_failed_search_gives_one_empty_item(self):
        for listing in ({"items": []}, {"error": {"message": "timeout"}}):
            out = self.run_booking_code("Pick Callbacks to Replace", {"Build Booked Result": [self.BOOKED]}, [listing])
            self.assertEqual(len(out), 1)
            self.assertIsNone(out[0]["cancelId"])
        self.assertTrue(self.run_booking_code("Pick Callbacks to Replace", {"Build Booked Result": [self.BOOKED]},
                                              [{"error": {"message": "timeout"}}])[0]["searchFailed"])

    def test_the_result_says_how_many_callbacks_were_replaced(self):
        picked = [{"cancelId": "cdlslotOLD"}, {"cancelId": "cdlslotOLD2"}]
        both_ok = self.run_booking_code("Finish Booking Result", {
            "Build Booked Result": [self.BOOKED], "Pick Callbacks to Replace": picked,
            "Cancel Replaced Callback": [{}, {}]}, [{}, {}])
        self.assertEqual(len(both_ok), 1)
        self.assertEqual((both_ok[0]["replacedPrevious"], both_ok[0]["replaceFailed"]), (2, False))
        one_failed = self.run_booking_code("Finish Booking Result", {
            "Build Booked Result": [self.BOOKED], "Pick Callbacks to Replace": picked,
            "Cancel Replaced Callback": [{}, {"error": {"message": "403"}}]}, [{}, {}])
        self.assertEqual((one_failed[0]["replacedPrevious"], one_failed[0]["replaceFailed"]), (1, True))

    def test_an_unbooked_result_passes_through_unchanged(self):
        unbooked = {"status": "slot_taken", "booked": False, "phone": "+12065550101"}
        out = self.run_booking_code("Finish Booking Result", {"Build Booked Result": [unbooked]}, [unbooked])
        self.assertEqual(out, [{**unbooked, "replacedPrevious": 0, "replaceFailed": False}])

    def test_nothing_found_means_zero_replaced_and_no_failure(self):
        out = self.run_booking_code("Finish Booking Result", {
            "Build Booked Result": [self.BOOKED], "Pick Callbacks to Replace": [{"cancelId": None}]}, [{"cancelId": None}])
        self.assertEqual((out[0]["replacedPrevious"], out[0]["replaceFailed"], out[0]["status"]), (0, False, "booked"))

    # --- recruiter emails after the caller has the answer (as in the client build) -------------------------------

    def with_emails(self, workflow=None):
        import copy
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_modular_workflows import add_recruiter_emails
        return add_recruiter_emails(copy.deepcopy(workflow or self.workflows["intake"]), "cred-123", "Gmail Accelent AI")

    def test_the_caller_hears_whether_an_earlier_callback_was_replaced(self):
        body = {n["name"]: n for n in self.workflows["intake"]["nodes"]}["Respond Booking Result"]["parameters"]["responseBody"]
        self.assertIn("replacedPrevious:$json.replacedPrevious||0", body)

    def test_recruiter_emails_run_after_the_answer_to_the_caller(self):
        wf = self.with_emails()
        targets = [t["node"] for t in wf["connections"]["Respond Booking Result"]["main"][0]]
        self.assertIn("Build Recruiter Email", targets)
        self.assertEqual([t["node"] for t in wf["connections"]["Build Recruiter Email"]["main"][0]], ["Email Recruiters"])
        gmail = {n["name"]: n for n in wf["nodes"]}["Email Recruiters"]
        self.assertEqual(gmail["type"], "n8n-nodes-base.gmail")
        self.assertEqual(gmail["parameters"]["sendTo"], "toshiki@accelentai.com")
        self.assertEqual(gmail["credentials"], {"gmailOAuth2": {"id": "cred-123", "name": "Gmail Accelent AI"}})
        self.assertEqual(gmail.get("onError"), "continueRegularOutput")  # a mail problem never fails the call's record

    def test_recruiter_emails_patch_is_idempotent_and_touches_nothing_else(self):
        before = self.workflows["intake"]
        once, twice = self.with_emails(), self.with_emails(self.with_emails())
        self.assertEqual(len(once["nodes"]), len(before["nodes"]) + 2)
        self.assertEqual(once, twice)
        old = {n["name"]: n for n in before["nodes"]}
        self.assertTrue(all(n == old[n["name"]] for n in once["nodes"] if n["name"] in old))

    def recruiter_email(self, result):
        code = {n["name"]: n for n in self.with_emails()["nodes"]}["Build Recruiter Email"]["parameters"]["jsCode"]
        runner = ("const [code, item] = process.argv.slice(1).map((v, i) => i ? JSON.parse(v) : v);"
                  "console.log(JSON.stringify(new Function('$input', code)({ first: () => ({ json: item }) }).map(i => i.json)));")
        return json.loads(subprocess.run(["node", "-e", runner, code, json.dumps(result)],
                                         capture_output=True, text=True, check=True).stdout)

    LEAD = {"firstName": "Carlos", "lastName": "Rivera", "phone": "+16727274656", "city": "Dallas", "state": "TX",
            "zipCode": "75201", "experienceText": "5 years", "readiness": "within 7 days", "temperature": "MEDIUM",
            "preferredCallbackTime": "2026-09-28T10:00:00", "startUtc": "2026-09-28T17:00:00.000Z"}  # summer: no DST question

    def test_a_booked_callback_emails_the_recruiters_with_the_lead_details(self):
        (mail,) = self.recruiter_email({**self.LEAD, "status": "booked", "booked": True})
        self.assertEqual(mail["subject"], "✅ Callback Appointment Scheduled with Lead Carlos Rivera MEDIUM")
        for text in ("Carlos Rivera", "Dallas, TX 75201", "+16727274656", "5 years", "within 7 days", "MEDIUM",
                     "Mon, Sep 28, 10:00 AM Pacific", "https://cdl-admin.accelentai.com"):
            self.assertIn(text, mail["html"], text)

    def test_a_replaced_callback_says_so_in_the_email(self):
        (mail,) = self.recruiter_email({**self.LEAD, "status": "booked", "booked": True, "replacedPrevious": 1})
        self.assertIn("(moved)", mail["subject"])
        self.assertIn("replaces 1 earlier callback", mail["html"])

    def test_a_booking_that_needs_a_person_sends_the_manual_action_email(self):
        (mail,) = self.recruiter_email({**self.LEAD, "status": "manual_followup", "booked": False, "startUtc": None})
        self.assertEqual(mail["subject"], "⚠️ Appointment Booking Failed – Manual Action Required")
        self.assertIn("manually schedule", mail["html"])
        self.assertIn("2026-09-28T10:00:00", mail["html"])  # the requested time, as asked

    def test_no_email_while_the_caller_is_still_choosing_a_time(self):
        for status in ("slot_taken", "slot_unavailable", "invalid_request"):
            self.assertEqual(self.recruiter_email({**self.LEAD, "status": status, "booked": False}), [], status)

    def test_caller_words_cannot_inject_html_into_the_email(self):
        (mail,) = self.recruiter_email({**self.LEAD, "firstName": "<script>x</script>", "status": "booked", "booked": True})
        self.assertNotIn("<script>", mail["html"])
        self.assertIn("&lt;script&gt;", mail["html"])

    def existing_lead_prompt(self):
        return (ROOT / "config" / "vapi" / "prompts" / "existing-lead.md").read_text(encoding="utf-8")

    def test_the_existing_lead_agent_says_moved_only_when_the_tool_says_it_replaced_a_callback(self):
        prompt = self.existing_lead_prompt()
        self.assertIn("`replacedPrevious`", prompt)
        self.assertIn("I've moved your callback", prompt)
        self.assertIn("If `replacedPrevious` is missing or 0", prompt)

    def test_a_returning_caller_who_wants_to_cancel_is_offered_a_move_first_and_never_told_it_is_cancelled(self):
        """Owner decision 2026-10-27: no cancel tool, on purpose. Cancelling loses a lead, so offer to move it first."""
        prompt = self.existing_lead_prompt()
        self.assertIn("**Wants to cancel", prompt)
        self.assertIn("offer to move it first", prompt)
        self.assertIn("A recruiter will confirm", prompt)
        self.assertIn("Never say the callback is cancelled", prompt)
        self.assertIn("you cannot cancel", prompt)

    def test_the_existing_lead_prompt_has_an_example_for_a_moved_callback_and_for_a_cancel_request(self):
        prompt = self.existing_lead_prompt()
        self.assertIn("### Moving a callback", prompt)
        self.assertIn("### Wants to cancel", prompt)

    # --- a cancel request reaches the recruiters (no cancel tool, on purpose: owner decision 2026-10-27) ---------

    def test_the_call_analysis_can_label_a_call_as_a_cancel_request(self):
        desired = json.loads((ROOT / "config" / "vapi" / "desired.json").read_text(encoding="utf-8"))
        intent = desired["shared"]["analysisPlan"]["structuredDataPlan"]["schema"]["properties"]["callIntent"]
        self.assertEqual(intent["enum"], ["new_application", "reschedule", "status_check", "cancel_request", "other"])
        self.assertIn("did not pick a new time", intent["description"])

    def test_post_call_normalizing_carries_the_call_intent_and_the_name(self):
        code = {n["name"]: n for n in self.workflows["post_call"]["nodes"]}["Normalize Post Call"]["parameters"]["jsCode"]
        self.assertIn("callIntent", code)
        self.assertIn("fullName", code)

    def with_cancel_email(self, workflow=None):
        import copy
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from build_modular_workflows import add_cancel_request_email
        return add_cancel_request_email(copy.deepcopy(workflow or self.workflows["post_call"]), "cred-123", "Gmail Accelent AI")

    def test_the_cancel_request_email_hangs_off_normalizing_so_zoho_is_not_needed(self):
        wf = self.with_cancel_email()
        targets = [t["node"] for t in wf["connections"]["Normalize Post Call"]["main"][0]]
        self.assertIn("Build Cancel Request Email", targets)
        self.assertIn("Find Candidate for Post Call", targets)  # the existing path is untouched
        self.assertEqual([t["node"] for t in wf["connections"]["Build Cancel Request Email"]["main"][0]],
                         ["Email Recruiters About Cancel"])
        gmail = {n["name"]: n for n in wf["nodes"]}["Email Recruiters About Cancel"]
        self.assertEqual(gmail["parameters"]["sendTo"], "toshiki@accelentai.com")
        self.assertEqual(gmail["credentials"], {"gmailOAuth2": {"id": "cred-123", "name": "Gmail Accelent AI"}})
        self.assertEqual(gmail.get("onError"), "continueRegularOutput")

    def test_the_cancel_email_patch_is_idempotent_and_touches_nothing_else(self):
        before = self.workflows["post_call"]
        once, twice = self.with_cancel_email(), self.with_cancel_email(self.with_cancel_email())
        self.assertEqual(len(once["nodes"]), len(before["nodes"]) + 2)
        self.assertEqual(once, twice)

    def cancel_email(self, item):
        code = {n["name"]: n for n in self.with_cancel_email()["nodes"]}["Build Cancel Request Email"]["parameters"]["jsCode"]
        runner = ("const [code, item] = process.argv.slice(1).map((v, i) => i ? JSON.parse(v) : v);"
                  "console.log(JSON.stringify(new Function('$input', code)({ first: () => ({ json: item }) }).map(i => i.json)));")
        return json.loads(subprocess.run(["node", "-e", runner, code, json.dumps(item)], capture_output=True, text=True, check=True).stdout)

    CALL = {"callIntent": "cancel_request", "fullName": "Carlos Rivera", "phone": "+16727274656", "callId": "call-1",
            "city": "Dallas", "state": "TX", "summary": "Caller found another job and wants to cancel."}

    def test_only_a_cancel_request_sends_the_email(self):
        for intent in ("reschedule", "new_application", "status_check", "other", ""):
            self.assertEqual(self.cancel_email({**self.CALL, "callIntent": intent}), [], intent)
        (mail,) = self.cancel_email(self.CALL)
        self.assertEqual(mail["subject"], "⚠️ Callback cancel request – Carlos Rivera")
        for text in ("Carlos Rivera", "+16727274656", "Dallas, TX", "found another job", "not removed",
                     "https://cdl-admin.accelentai.com"):
            self.assertIn(text, mail["html"], text)

    def test_caller_words_cannot_inject_html_into_the_cancel_email(self):
        (mail,) = self.cancel_email({**self.CALL, "summary": "<img src=x onerror=alert(1)>"})
        self.assertNotIn("<img", mail["html"])

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
