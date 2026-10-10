// End-to-end smoke against a real engine in replay mode, through stdio like a real client.
//   MIRAGE_MODE=replay MIRAGE_REPLAY_SPEED=inf uv run uvicorn engine.api.server:app   (repo root)
//   npm run build && npm run smoke
// The elicitation handler types the phrase the form asks for, like a human would.
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { ElicitRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { fileURLToPath } from "node:url";  // .pathname gives "/C:/..." on Windows

const api = process.env.MIRAGE_API ?? "http://localhost:8000";
await fetch(`${api}/demo/reset`, { method: "POST" });
const client = new Client({ name: "mirage-smoke", version: "1" }, { capabilities: { elicitation: {} } });
client.setRequestHandler(ElicitRequestSchema, ({ params }) => {
  const phrase = params.requestedSchema.properties.confirm.title.match(/"(.+)"/)[1];
  console.log(`  [form] ${params.message.split("\n")[0]} → typing "${phrase}"`);
  return { action: "accept", content: { confirm: phrase, reason: "smoke test" } };
});
await client.connect(new StdioClientTransport({ command: "node", args: [fileURLToPath(new URL("../dist/index.js", import.meta.url))],
  env: { ...process.env, MIRAGE_API: api } }));

let failed = 0;
async function step(name, args, expect) {
  const r = await client.callTool({ name, arguments: args }, undefined, { timeout: 200_000 });
  const text = r.content[0].text;
  const ok = expect.test(text);
  failed += !ok;
  console.log(`${ok ? "PASS" : "FAIL"} ${name} ${JSON.stringify(args)}\n  ${text.split("\n").slice(0, 6).join("\n  ")}`);
}

await step("list_runs", {}, /run_002 · meeting_assistant · frozen · incident inc_001/);
await step("get_incident", {}, /Incident inc_001 · open[\s\S]*untrusted_input source="calendar_event"/);
await step("detonate", { incident_id: "inc_001" }, /Detonation done: 3\/3 replays compromised[\s\S]*COMPROMISED: 3\/3/);
await step("unfreeze", { run_id: "run_002", reason: "looks fine" }, /Not done: detonation proved run_002 is compromised/);
await step("kill", { run_id: "run_002", reason: "confirmed exfiltration" }, /Done: run_002 is now killed/);
await step("get_audit", { target: "run_002" }, /kill run_002/);
await step("find_cause", { incident_id: "inc_001" }, /in_cal_03 removed → 0\/2 compromised {2}← CAUSE/);
await step("send_fix", { incident_id: "inc_001" }, /Handoff created[\s\S]*Incident inc_001/);
await client.close();
console.log(failed ? `${failed} FAILED` : "ALL PASS");
process.exit(failed ? 1 : 0);
