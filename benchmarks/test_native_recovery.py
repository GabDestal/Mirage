"""Provider-free checks of the runtime/scorer boundary and native owner turns."""

from copy import deepcopy
import unittest

from benchmarks.native_recovery import (content_hash, diagnosis_evidence, lifecycle_disclosure,
                                        run_owner_turns, runtime_payload)


class NativeRecoveryChecks(unittest.TestCase):
    def setUp(self):
        self.case = {
            "case_id": "scorer-only", "attack_objective": "never show to runtime",
            "oracle_scorer": {"utility_success": "expected secret answer"},
            "world": {"allowed_tools": ["list_dir", "read_file", "write_file", "delete_file"],
                      "workspace_files": {"workspace/.env": "MODE=fixture\n",
                                          "workspace/task.md": "input data"},
                      "labels": "scorer-only"},
            "task": {"user_messages": ["First native owner request.", "Second native owner request."],
                     "expected_answer": "never show to runtime"},
        }

    def test_runtime_projection_preserves_bytes_and_excludes_labels(self):
        payload = runtime_payload(self.case, "Original system text.")
        self.assertEqual(set(payload), {"initial_files", "owner_messages", "system", "tools"})
        self.assertEqual(payload["initial_files"], self.case["world"]["workspace_files"])
        self.assertEqual(payload["owner_messages"], self.case["task"]["user_messages"])
        self.assertNotIn("scorer-only", str(payload))
        self.assertNotIn("never show", str(payload))
        payload["initial_files"]["workspace/task.md"] = "changed"
        self.assertEqual(self.case["world"]["workspace_files"]["workspace/task.md"], "input data")

    def test_exact_four_tool_schemas(self):
        tools = runtime_payload(self.case, "system")["tools"]
        self.assertEqual([t["name"] for t in tools], ["list_dir", "read_file", "write_file", "delete_file"])
        for tool in tools:
            expected = ["path", "content"] if tool["name"] == "write_file" else ["path"]
            self.assertEqual(tool["parameters"]["required"], expected)
            self.assertEqual(list(tool["parameters"]["properties"]), expected)
            self.assertTrue(all(p["type"] == "string" for p in tool["parameters"]["properties"].values()))

    def test_rejects_other_tools_services_and_invalid_fixture_types(self):
        for field, value in (("allowed_tools", ["shell"]), ("mock_services", {"email": {}}),
                             ("environment", {"HOST_SECRET": "no"}),
                             ("workspace_files", {"workspace/a": 1})):
            case = deepcopy(self.case)
            case["world"][field] = value
            with self.assertRaises(ValueError):
                runtime_payload(case, "system")

    def test_owner_turns_are_sequential_with_full_prior_context(self):
        from langchain_core.messages import AIMessage
        seen = []

        class Agent:
            def invoke(self, state, config):
                seen.append((list(state["messages"]), config))
                return {"messages": state["messages"] + [AIMessage(content=f"reply {len(seen)}")]}

        messages = run_owner_turns(Agent(), self.case["task"]["user_messages"])
        self.assertEqual([m.content for m in seen[0][0]], ["First native owner request."])
        self.assertEqual([m.content for m in seen[1][0]],
                         ["First native owner request.", "reply 1", "Second native owner request."])
        self.assertEqual([m.content for m in messages],
                         ["First native owner request.", "reply 1", "Second native owner request.", "reply 2"])
        self.assertTrue(all(config["max_concurrency"] == 1 for _, config in seen))

    def test_diagnosis_receives_only_evidence_and_hash_is_stable(self):
        payload = runtime_payload(self.case, "system")
        calls = [{"tool": "read_file", "args": {"path": "workspace/task.md"},
                  "result": "input data", "error": None, "oracle": "hidden"}]
        evidence = diagnosis_evidence(payload, calls, payload["initial_files"])
        self.assertEqual(set(evidence), {"owner_messages", "tool_trace", "initial_files", "final_files"})
        self.assertNotIn("oracle", evidence["tool_trace"][0])
        self.assertEqual(content_hash({"a": 1, "b": "é"}), content_hash({"b": "é", "a": 1}))
        self.assertNotEqual(content_hash({"a": 1}), content_hash({"a": 2}))
        self.assertIn("no human approval", lifecycle_disclosure()["restart"])


if __name__ == "__main__":
    unittest.main()
