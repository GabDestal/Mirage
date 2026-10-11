import { mkdtemp, mkdir, readFile, realpath, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { ElicitRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { createChatService } from "../src/chat.js";
import { createServer } from "../src/server.js";
import { digest, digestBytes, type CommandRunner, type RepairJob } from "../src/repair-supervisor.js";
import { inspectMergedPullRequest, recoveryConfig, RecoverySupervisor, type RecoveryState } from "../src/recovery.js";

const base = "a".repeat(40), candidate = "b".repeat(40), merged = "c".repeat(40), tree = "d".repeat(40);
const pr = { url: "https://github.com/GabDestal/Mirage/pull/123", number: 123, baseRefName: "special-improvements",
  state: "MERGED", isDraft: false, headRefOid: candidate, mergeCommit: { oid: merged } };
const job: RepairJob = { id: "job", incident_id: "incident", repository: "GabDestal/Mirage", base_branch: "special-improvements",
  base_sha: base, snapshot_digest: "pending", baseline_digest: digest([]), status: "pr_open", candidate_sha: candidate,
  verification: { attack_blocked: "3/3", legit_task_completed: "3/3", clean_task_completed: "1/1" },
  pr_url: pr.url, created_at: "2026-10-11", updated_at: "2026-10-11" };
const receipt = (value: unknown, code = 0) => ({ code, stdout: JSON.stringify(value), stderr: "" });

describe("actual merged PR identity", () => {
  it.each([
    { state: "OPEN" }, { baseRefName: "main" }, { headRefOid: "e".repeat(40) }, { mergeCommit: null }, { isDraft: true },
    { url: "https://github.com/attacker/Mirage/pull/123" },
  ])("refuses an untrusted merge receipt %j", (change) => {
    expect(() => inspectMergedPullRequest(receipt({ ...pr, ...change }), job, job.repository)).toThrow();
  });
  it("accepts a real merged receipt while preserving candidate and squash revisions", () => {
    expect(inspectMergedPullRequest(receipt(pr), job, job.repository).mergeCommit.oid).toBe(merged);
    expect(merged).not.toBe(candidate);
  });
});

async function harness({ changedTree = false, badVerification = false, changedPolicy = false, missingPolicyRevision = false,
  scriptedCapture = false, badCapture = false, copiedCheckpoint = false, badCheckpoint = false } = {}) {
  const repoPath = await realpath(await mkdtemp(join(tmpdir(), "mirage-recovery-test-")));
  const checkout = join(repoPath, "isolated");
  await mkdir(checkout);
  const checkpointPath = join(repoPath, "original-services.json");
  await writeFile(checkpointPath, JSON.stringify({ calendar: [{ description: "untrusted synthetic attack" }], contacts: [], inbox: [], outbox: [] }));
  const config = { MEETING_ASSISTANT_MODEL_ID: "synthetic-model", DEMO_USER_EMAIL: "user@mirage-demo.com" };
  const legit = { required: [{ tool: "send_email", args: { to: config.DEMO_USER_EMAIL }, nonempty: ["subject", "body"],
    contains: { body: ["Synthetic meeting"] } }] };
  const spec = { name: "meeting_assistant", owner: "liam", tools: ["read_calendar", "send_email"],
    allow: { tools: ["read_calendar", "send_email"], email_to: [config.DEMO_USER_EMAIL], url_hosts: [] },
    entrypoint: "agents.run_demo_fleet:meeting_assistant", legit };
  const snapshot = { incident_id: "incident", run_id: "old", agent: spec.name, task: "Original useful task",
    entrypoint: spec.entrypoint, model_id: scriptedCapture ? "ScriptedModel" : config.MEETING_ASSISTANT_MODEL_ID,
    legit, policy: { canary: "FLAG{team26-canary}" },
    model_calls: [{ request: { temperature: 1 } }] };
  const cleanSnapshot = { ...snapshot, incident_id: "clean" };
  const snapshotJson = JSON.stringify(snapshot).replace('"temperature":1', '"temperature":1.0');
  const cleanJson = JSON.stringify(cleanSnapshot).replace('"temperature":1', '"temperature":1.0');
  const context = { job: { ...job, snapshot_digest: digestBytes(snapshotJson), verification: {
    ...job.verification!, clean_snapshot_digest: digestBytes(cleanJson) } }, snapshot,
    clean_snapshot: cleanSnapshot, baseline_effects: [], snapshot_json: snapshotJson, clean_snapshot_json: cleanJson,
    baseline_json: "[]", policy_digest: digest(snapshot.policy) };
  const effectivePolicy = changedPolicy ? { ...snapshot.policy, rule_revision: "f".repeat(64) } : snapshot.policy;
  let state: RecoveryState | undefined, moved = false;
  let configSourceDigest: string | undefined;
  const commands: { command: string; args: string[]; cwd: string; env?: NodeJS.ProcessEnv }[] = [];
  const requests: { path: string; body?: any }[] = [];
  const run: CommandRunner = async (command, args, options) => {
    commands.push({ command, args, ...options });
    if (command === "gh") return receipt(pr);
    if (command === "orca") return receipt({ ok: true, result: { worktree: args[1] === "show"
      ? { path: repoPath, repoId: "registered-repo" } : { path: checkout, id: `repo::${checkout}` } } });
    if (command === "git") {
      let stdout = "";
      if (args[0] === "rev-parse") stdout = args[1] === "HEAD" ? (moved ? candidate : merged)
        : args[1].startsWith(candidate) ? tree : changedTree ? "e".repeat(40) : tree;
      return { code: 0, stdout, stderr: "" };
    }
    if (args.includes("engine.cli")) {
      const runs = args[args.indexOf("--runs") + 1];
      const raw = await readFile(join(options.env!.MIRAGE_SNAPSHOTS!, `${args[args.indexOf("--incident") + 1]}.json`), "utf8");
      expect(raw).toContain('"temperature":1.0');
      const policy = JSON.parse(await readFile(args[args.indexOf("--policy-file") + 1], "utf8"));
      expect(policy).toEqual(effectivePolicy);
      return receipt({ incident_id: args[args.indexOf("--incident") + 1], attack_blocked: `${runs}/${runs}`,
        legit_task_completed: `${runs}/${runs}`, passed: !badVerification,
        policy_revisions: policy.rule_revision && !missingPolicyRevision ? [policy.rule_revision] : [],
        effects: Array.from({ length: Number(runs) }, (_, index) => ({ detonation_id: "synthetic", run_index: index + 1,
          step: 1, tool: "send_email", args: { to: config.DEMO_USER_EMAIL, subject: "Brief", body: "Synthetic meeting" }, violates: [], error: null })) },
      badVerification ? 1 : 0);
    }
    const request = JSON.parse(await readFile(args[args.indexOf("--request") + 1], "utf8"));
    const prepared = { agent_spec: spec, checkpoint_digest: request.checkpoint_digest, config_digest: digest(config) };
    const phase = args[args.indexOf("--phase") + 1];
    if (phase === "prepare") requests.push({ path: "factory_registered" });
    else {
      expect(request.original_run_id).toBe("old");
      expect(request.queued_run_id).toBe("new");
      expect(request.task).toBe(snapshot.task);
      state = { ...state!, status: "completed" };
    }
    await writeFile(args[args.indexOf("--output") + 1], JSON.stringify({ ...prepared,
      ...(phase === "launch" && { run_id: "new", run: { restarted_from: "old", agent: spec.name, task: snapshot.task } }) }));
    return receipt({});
  };
  const fetcher: typeof fetch = async (input, init) => {
    const path = new URL(String(input)).pathname;
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    requests.push({ path, body });
    if (path.endsWith("/context")) return Response.json(context);
    if (path.endsWith("/provenance")) {
      return Response.json({ policy_digest: digest(effectivePolicy), policy: effectivePolicy, agent_spec: spec,
        config, config_digest: digest(config), config_source_digest: configSourceDigest ?? null });
    }
    if (path.endsWith("/report")) {
      if (body.clean_control) expect(String(init?.body)).toContain(`"snapshot":${cleanJson}`);
      state = { status: "prepared", report: { ...body, verification: null, clean_control: null } }; return Response.json(state);
    }
    return Response.json(state);
  };
  const runtime = { repository: job.repository, repoPath, baseSha: base, python: "python",
    supervisorToken: "synthetic-test-only", api: "http://127.0.0.1:8000", checkpointPath, originalConfig: config,
    liveVerification: true, run, fetch: fetcher };
  let configured = runtime;
  if (scriptedCapture) {
    const originalPath = join(repoPath, "original-snapshot.json"), sourcePath = join(repoPath, "original-config.json");
    await writeFile(originalPath, snapshotJson);
    const sourceReceipt = { agent_name: spec.name, entrypoint: spec.entrypoint, task: snapshot.task, legit,
      effective_agent_model_id: config.MEETING_ASSISTANT_MODEL_ID, recipient: config.DEMO_USER_EMAIL,
      region: "us-east-1", temperature: 0, git_status: "clean", code_revision: base,
      original_snapshot_path: originalPath, original_snapshot_sha256: badCapture ? "0".repeat(64) : digestBytes(snapshotJson),
      original_services_path: checkpointPath, original_services_sha256: digestBytes(await readFile(checkpointPath, "utf8")),
      nonsecret_environment: config, captured_at: "2026-10-11", code_root: repoPath, source_sha256: { "agents/example.py": tree } };
    await writeFile(sourcePath, JSON.stringify(sourceReceipt));
    const copiedPath = join(repoPath, "private-checkpoint.json");
    if (copiedCheckpoint) await writeFile(copiedPath, badCheckpoint ? "{}" : await readFile(checkpointPath));
    const loaded = await recoveryConfig(runtime, { MIRAGE_RECOVERY_CHECKPOINT: copiedCheckpoint ? copiedPath : checkpointPath,
      MIRAGE_RECOVERY_CONFIG_SOURCE: sourcePath });
    configSourceDigest = digest(sourceReceipt);
    expect(loaded!.configSourceDigest).toBe(configSourceDigest);
    configured = loaded as typeof runtime;
  }
  const supervisor = new RecoverySupervisor(configured);
  return { supervisor, commands, requests, checkout, get state() { return state!; },
    approve() { state = { ...state!, status: "queued", new_run_id: "new", report: {
      ...state!.report, verification: state!.report.verification ?? undefined, clean_control: state!.report.clean_control ?? undefined } }; },
    move() { moved = true; } };
}

it("reuses equal-tree squash proof and registers before recording preparation", async () => {
  const h = await harness();
  const state = await h.supervisor.prepareRecovery("job");
  expect(state.status).toBe("prepared");
  expect(state.report.verified_sha).toBe(candidate);
  expect(state.report.merged_sha).toBe(merged);
  expect(h.commands.some((call) => call.args.includes("engine.cli"))).toBe(false);
  const create = h.commands.find((call) => call.command === "orca" && call.args[1] === "create")!;
  expect(create.args.slice(create.args.indexOf("--repo"), create.args.indexOf("--repo") + 2)).toEqual(["--repo", "id:registered-repo"]);
  expect(create.args).toContain("special-improvements");
  expect(create.args.slice(create.args.indexOf("--setup"), create.args.indexOf("--setup") + 2)).toEqual(["--setup", "skip"]);
  expect(h.requests.findIndex((r) => r.path === "factory_registered")).toBeLessThan(h.requests.findIndex((r) => r.path.endsWith("/report")));
  expect(h.commands.filter((call) => call.command === "git" && call.args.includes("checkout")).every((call) => call.cwd === h.checkout)).toBe(true);
});

it("verifies a changed merged tree with private attack and clean state", async () => {
  const h = await harness({ changedTree: true });
  const state = await h.supervisor.prepareRecovery("job");
  expect(state.report.verified_sha).toBe(merged);
  const report = h.requests.find((r) => r.path.endsWith("/report"))!.body;
  expect(report.verification.result.attack_blocked).toBe("3/3");
  expect(report.clean_control.result.legit_task_completed).toBe("1/1");
  const verifies = h.commands.filter((call) => call.args.includes("engine.cli"));
  expect(verifies).toHaveLength(2);
  expect(verifies.every((call) => call.cwd === h.checkout && call.env?.MIRAGE_DB?.includes("mirage-verification-")
    && call.env?.MEETING_ASSISTANT_MODEL_ID === "synthetic-model" && !call.env?.MIRAGE_REPAIR_SUPERVISOR_TOKEN)).toBe(true);
  expect(verifies[0].env?.MIRAGE_DB).not.toBe(verifies[1].env?.MIRAGE_DB);
});

it("failed merged verification cannot prepare recovery", async () => {
  const h = await harness({ changedTree: true, badVerification: true });
  await expect(h.supervisor.prepareRecovery("job")).rejects.toThrow();
  expect(h.commands.filter((call) => call.args.includes("engine.cli"))).toHaveLength(1);
  expect(h.requests.some((r) => r.path.endsWith("/report"))).toBe(false);
});

it("policy changes require merged verification even when squash trees match", async () => {
  const h = await harness({ changedPolicy: true });
  const state = await h.supervisor.prepareRecovery("job");
  expect(state.report.verified_sha).toBe(merged);
  expect(h.commands.filter((call) => call.args.includes("engine.cli"))).toHaveLength(2);
});

it("changed-rule proof without the actual pinned revision cannot prepare recovery", async () => {
  const h = await harness({ changedPolicy: true, missingPolicyRevision: true });
  await expect(h.supervisor.prepareRecovery("job")).rejects.toThrow("current rule revision");
  expect(h.requests.some((r) => r.path.endsWith("/report"))).toBe(false);
});

it("uses provider configuration from a trusted snapshot-bound scripted capture receipt", async () => {
  const h = await harness({ scriptedCapture: true });
  const state = await h.supervisor.prepareRecovery("job");
  expect(state.report.config.MEETING_ASSISTANT_MODEL_ID).toBe("synthetic-model");
  expect(state.report.config_source_digest).toMatch(/^[a-f0-9]{64}$/);
  expect(state.status).toBe("prepared");
});

it("refuses a scripted model override when its trusted original snapshot hash changed", async () => {
  const h = await harness({ scriptedCapture: true, badCapture: true });
  await expect(h.supervisor.prepareRecovery("job")).rejects.toThrow("configuration");
  expect(h.commands).toHaveLength(0);
});

it("accepts a byte-identical private checkpoint copy without changing source provenance", async () => {
  const h = await harness({ scriptedCapture: true, copiedCheckpoint: true });
  expect((await h.supervisor.prepareRecovery("job")).status).toBe("prepared");
});

it("refuses a private checkpoint copy with different bytes", async () => {
  const h = await harness({ scriptedCapture: true, copiedCheckpoint: true, badCheckpoint: true });
  await expect(h.supervisor.prepareRecovery("job")).rejects.toThrow("configuration");
  expect(h.commands.some((command) => command.command === "orca")).toBe(false);
});

it("routes operator-only prepare and approved launch without model or approval calls", async () => {
  const state = { status: "prepared", report: {} } as RecoveryState;
  const prepareRecovery = vi.fn(async () => state), launchApprovedRecovery = vi.fn(async () => state);
  const stream = vi.fn(async () => { throw new Error("A model must not be called"); });
  const service = createChatService({ provider: { stream }, recovery: { prepareRecovery, launchApprovedRecovery } });
  await new Promise<void>((resolve) => service.http.listen(0, "127.0.0.1", resolve));
  const address = service.http.address();
  if (!address || typeof address === "string") throw new Error("Missing loopback address");
  const post = (path: string, body: unknown, headers: Record<string, string> = {}) => fetch(`http://127.0.0.1:${address.port}${path}`,
    { method: "POST", headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(body) });
  try {
    expect((await post("/chat/recovery/job/prepare", {}, { origin: "https://untrusted.invalid" })).status).toBe(403);
    expect((await post("/chat/recovery/job/prepare", { approve: true })).status).toBe(400);
    expect((await post("/chat/recovery/incident/launch", { queued_run_id: "new", reason: "auto approve" })).status).toBe(400);
    expect(prepareRecovery).not.toHaveBeenCalled(); expect(launchApprovedRecovery).not.toHaveBeenCalled();
    expect((await post("/chat/recovery/job/prepare", {})).status).toBe(200);
    expect((await post("/chat/recovery/incident/launch", { queued_run_id: "new" })).status).toBe(200);
    expect(prepareRecovery).toHaveBeenCalledExactlyOnceWith("job");
    expect(launchApprovedRecovery).toHaveBeenCalledExactlyOnceWith("incident", "new");
    expect(stream).not.toHaveBeenCalled();
  } finally { await service.close(); }
});

it("MCP preparation never approves and queue launch fails closed without human confirmation", async () => {
  const prepareRecovery = vi.fn(async () => ({ status: "prepared", report: {} }) as RecoveryState);
  const launchApprovedRecovery = vi.fn(async () => ({ status: "running", report: {} }) as RecoveryState);
  const server = createServer({ recovery: { prepareRecovery, launchApprovedRecovery } });
  const client = new Client({ name: "recovery-test", version: "1" }, { capabilities: { elicitation: { form: {} } } });
  let approve = false;
  client.setRequestHandler(ElicitRequestSchema, async () => approve
    ? { action: "accept", content: { confirm: "launch new", reason: "Human reviewed this approved queue" } } : { action: "decline" });
  const [a, b] = InMemoryTransport.createLinkedPair();
  await server.connect(a); await client.connect(b);
  try {
    const tools = (await client.listTools()).tools.map((tool) => tool.name);
    expect(tools).toContain("prepare_recovery"); expect(tools).toContain("launch_approved_recovery");
    expect(tools).not.toContain("approve_restart");
    await client.callTool({ name: "prepare_recovery", arguments: { job_id: "job" } });
    expect(prepareRecovery).toHaveBeenCalledExactlyOnceWith("job");
    expect((await client.callTool({ name: "launch_approved_recovery", arguments: { incident_id: "incident", queued_run_id: "new" } })).isError).toBe(true);
    expect(launchApprovedRecovery).not.toHaveBeenCalled();
    approve = true;
    await client.callTool({ name: "launch_approved_recovery", arguments: { incident_id: "incident", queued_run_id: "new" } });
    expect(launchApprovedRecovery).toHaveBeenCalledExactlyOnceWith("incident", "new");
  } finally { await client.close(); await server.close(); }
});

it("requires explicit approval and launches the exact queue at most once", async () => {
  const h = await harness();
  await h.supervisor.prepareRecovery("job");
  await expect(h.supervisor.launchApprovedRecovery("incident", "new")).rejects.toThrow("human-approved");
  h.approve();
  expect((await h.supervisor.launchApprovedRecovery("incident", "new")).status).toBe("completed");
  await expect(h.supervisor.launchApprovedRecovery("incident", "new")).rejects.toThrow("launched");
  expect(h.commands.filter((call) => call.args.includes("launch"))).toHaveLength(1);
});

it("refuses a moved merged checkout before executing the approved task", async () => {
  const h = await harness();
  await h.supervisor.prepareRecovery("job"); h.approve(); h.move();
  await expect(h.supervisor.launchApprovedRecovery("incident", "new")).rejects.toThrow("checkout changed");
  expect(h.commands.some((call) => call.args.includes("launch"))).toBe(false);
});
