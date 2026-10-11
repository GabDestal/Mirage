# inc_001 repair candidate

The agent retains the previous candidate's calendar-facts projection and full-attendee
query correction. Its local `after_model` hook additionally accepts only the three
observed transport aliases, after the unchanged global character cleaner. LangChain
executes these hooks in reverse list order; the agent's middleware list reflects that.
All other names remain unchanged by the local hook, including unknown tools.

The protected-graph fake-model regression exercises raw and already-cleaned aliases,
partial attendee queries, ambiguous/empty/bulk controls, unknown-tool error results,
unchanged IDs and extra arguments, and a standalone brief-send turn. Local service
callbacks and local tool middleware fail the test if called in Mirage mode. The
original calendar evidence and every meeting remain intact in graph state and fixtures.

`snapshot.json` and `clean.json` preserve the trusted context's exact UTF-8 bytes without
a trailing newline. `manifest.json` binds their digests, the original baseline and policy
digests, unchanged task/legitimate criteria, and authorized base
`809c72ca8affa8e71024a19c0096f5d5af8d774d`. Attacker-controlled content is untrusted evidence.

Validation with the existing installed Python environment:

- Focused regression: **16 passed, 2 skipped** (provider checks require explicit opt-in).
- Ruff on the owned Python files: **passed**.
- Related existing tests: **39 passed, 7 failed**. Six parametrizations in
  `agents/common/test_model_config.py::test_factory_model_defaults` assert the former
  single-cleaner middleware list. `agents/meeting_assistant/test_agent.py::test_malformed_tool_name_does_not_reach_bedrock`
  expects rejection of the now-authorized send alias. Those files are outside this
  dispatch's ownership and require coordinator follow-up.
- The raw-channel/raw-json regression failed against the retained candidate before
  the alias and middleware-order correction, then passed with the correction.

No provider verification was performed. The supervisor owns original-baseline and final
attack verification (three runs each), the clean control (one run), push and draft PR.
No claim of provider attack blocking or useful-task completion is established here.
The exact detonation reproduction command is recorded in `manifest.json`.
