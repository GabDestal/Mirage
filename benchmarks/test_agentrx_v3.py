"""Provider-free checks of the v3 lenient evidence parsers."""
import json
import unittest

from benchmarks.agentrx_phase2_v3 import checks, constraints, diagnosis, json_object


class AgentRxV3Parsers(unittest.TestCase):
    def test_fence_then_prose(self):
        text = '```json\n{"constraints": []}\n```\nThese are the constraints I found.'
        self.assertEqual(json_object(text), {'constraints': []})
        with self.assertRaises(ValueError):
            json_object('no json here')

    def test_compound_and_invalid_sources_dropped_with_counts(self):
        items = [{'id': 'S1', 'criterion': 'a', 'source': 'policy and tool_schema'},
                 {'id': 'S2', 'criterion': 'b', 'source': ['policy', 'tool_schema']},
                 {'id': 'S3', 'criterion': 'c', 'source': 'label'},
                 {'id': 'S4', 'criterion': 'd', 'source': 'policy'}]
        kept, dropped = constraints(json.dumps({'constraints': items}), 'static', 3)
        self.assertEqual([k['id'] for k in kept], ['S2', 'S4'])
        self.assertEqual(dropped, {'invalid_constraint_source': 2})
        kept, dropped = constraints(json.dumps({'constraints': [
            {'id': 'D1', 'criterion': 'x', 'source': 'trace', 'source_steps': [0]}]}), 'dynamic', 3)
        self.assertEqual((kept, dropped), ([], {'invalid_or_missing_evidence_indices': 1}))

    def test_partial_checker_marks_missing_unknown(self):
        rules = [{'id': 'S1'}, {'id': 'D1'}]
        text = json.dumps({'checks': [{'id': 'S1', 'evaluation': 'CLEAR_FAIL', 'evidence_steps': [2], 'reasoning': 'm2'}]})
        result, missing = checks(text, rules, 3)
        self.assertEqual(missing, 1)
        self.assertEqual([r['status'] for r in result], ['FAIL', 'UNKNOWN'])

    def test_null_step_with_empty_evidence_accepted(self):
        text = '{"critical_failure_step": null, "failure_category": 10, "explanation": "x", "evidence_steps": []}'
        self.assertIsNone(diagnosis(text, 3)['critical_failure_step'])
        with self.assertRaises(ValueError):
            diagnosis('{"critical_failure_step": 2, "failure_category": 1, "explanation": "x", "evidence_steps": []}', 3)
        with self.assertRaises(ValueError):
            diagnosis('{"critical_failure_step": 4, "failure_category": 1, "explanation": "x", "evidence_steps": [1]}', 3)


if __name__ == '__main__':
    unittest.main()
