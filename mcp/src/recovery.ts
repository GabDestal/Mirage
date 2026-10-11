// Trusted merged-revision launcher. This module never merges a PR or approves a restart.
import { createHash } from "node:crypto";
import { readFile, realpath } from "node:fs/promises";
import { join } from "node:path";
import { z } from "zod";
import { assertSanitized, digest, digestBytes, privateDirectory, privateJson, runCommand, serializeEvidenceReport, verifyCurrentCode,
  type CommandResult, type CommandRunner, type RepairConfig, type RepairJob, type Verification } from "./repair-supervisor.js";

const sha = z.string().regex(/^[a-f0-9]{40}$/);
const id = z.string().regex(/^[\w-]+$/);
const mergedPr = z.object({ url: z.string().url(), number: z.number().int().positive(),
  baseRefName: z.literal("special-improvements"), state: z.literal("MERGED"), headRefOid: sha,
  isDraft: z.literal(false), mergeCommit: z.object({ oid: sha }) });
export type MergedPullRequest = z.infer<typeof mergedPr>;

export function inspectMergedPullRequest(receipt: CommandResult, job: RepairJob, repository: string) {
  if (receipt.code !== 0) throw new Error("GitHub could not confirm the merged repair.");
  let pr: MergedPullRequest;
  try { pr = mergedPr.parse(JSON.parse(receipt.stdout)); }
  catch { throw new Error("The verified repair PR must be merged into special-improvements with an exact merge revision."); }
  const expected = `https://github.com/${repository}/pull/${pr.number}`;
  if (pr.url.toLowerCase() !== expected.toLowerCase() || pr.url !== job.pr_url
    || pr.headRefOid !== job.candidate_sha || job.repository.toLowerCase() !== repository.toLowerCase())
    throw new Error("Merged pull request does not match the verified repair and repository.");
  return pr;
}

type Spec = { name: string; owner: string; tools: string[]; allow: Record<string, unknown>;
  entrypoint: string; legit: Record<string, unknown> };
type Proof = { exit_code: number; result: Verification; replay_errors: number };
export type RecoveryReport = { repair_job_id: string; original_run_id: string; agent: string; task: string;
  pull_request: MergedPullRequest; merged_sha: string; candidate_tree: string; merged_tree: string;
  verified_sha: string; snapshot_digest: string; agent_spec: Spec; policy_digest: string;
  config: Record<string, string>; config_digest: string; checkpoint_digest: string; verification?: Proof;
  clean_control?: Proof & { snapshot: Record<string, any> } };
export type RecoveryState = { status: "prepared" | "queued" | "running" | "completed" | "failed";
  report: RecoveryReport; new_run_id?: string | null; error?: string | null };
type Context = { job: RepairJob; snapshot: Record<string, any>; clean_snapshot: Record<string, any>; baseline_effects: unknown[];
  snapshot_json: string; clean_snapshot_json: string; baseline_json: string; policy_digest: string };
export type RecoveryConfig = RepairConfig & { checkpointPath: string; originalConfig?: Record<string, string> };
export type RecoveryController = { prepareRecovery(jobId: string): Promise<RecoveryState>;
  launchApprovedRecovery(incidentId: string, queuedRunId: string): Promise<RecoveryState> };
type Prepared = { cwd: string; dir: string; request: Record<string, unknown>; report: RecoveryReport };

export async function recoveryConfig(config: RepairConfig, env: NodeJS.ProcessEnv = process.env): Promise<RecoveryConfig | undefined> {
  if (!env.MIRAGE_RECOVERY_CHECKPOINT) return undefined;
  const originalConfig = env.MIRAGE_RECOVERY_CONFIG
    ? z.record(z.string(), z.string()).parse(JSON.parse(await readFile(env.MIRAGE_RECOVERY_CONFIG, "utf8"))) : undefined;
  if (originalConfig) assertSanitized(originalConfig);
  return { ...config, checkpointPath: env.MIRAGE_RECOVERY_CHECKPOINT, originalConfig };
}

export class RecoverySupervisor implements RecoveryController {
  private run: CommandRunner;
  private prepared = new Map<string, Prepared>();
  private active = new Set<string>();
  private launched = new Set<string>();
  constructor(private config: RecoveryConfig) {
    this.run = config.run ?? runCommand;
    if (!["localhost", "127.0.0.1", "[::1]"].includes(new URL(config.api).hostname))
      throw new Error("Recovery engine must be on loopback.");
  }
  private async call<T>(path: string, body?: unknown, privateAccess = false): Promise<T> {
    const response = await (this.config.fetch ?? fetch)(this.config.api.replace(/\/$/, "") + path, {
      method: body === undefined ? "GET" : "POST", headers: { "content-type": "application/json",
        ...(privateAccess && { authorization: `Bearer ${this.config.supervisorToken}` }) },
      body: body === undefined ? undefined : typeof body === "string" ? body : JSON.stringify(body), signal: AbortSignal.timeout(15_000),
    });
    if (!response.ok) throw new Error("Engine refused recovery. Review the incident before trying again.");
    return await response.json() as T;
  }
  private async command(command: string, args: string[], cwd = this.config.repoPath) {
    const receipt = await this.run(command, args, { cwd });
    if (receipt.code !== 0) throw new Error("Required recovery command failed. The original stays contained.");
    return receipt.stdout.trim();
  }
  private async inspectCheckout(cwd: string, revision: string, tree: string) {
    if (await this.command("git", ["status", "--porcelain", "--untracked-files=all"], cwd)
      || await this.command("git", ["rev-parse", "HEAD"], cwd) !== revision
      || await this.command("git", ["rev-parse", "HEAD^{tree}"], cwd) !== tree)
      throw new Error("Merged checkout changed. Prepare the exact repair again.");
  }
  private async python(prepared: Pick<Prepared, "cwd" | "dir" | "request">, phase: "prepare" | "launch") {
    const requestPath = join(prepared.dir, `${phase}-request.json`), output = join(prepared.dir, `${phase}-receipt.json`);
    await privateJson(requestPath, prepared.request);
    const env: NodeJS.ProcessEnv = {};
    for (const key of ["PATH", "HOME", "TMPDIR", "LANG", "AWS_BEARER_TOKEN_BEDROCK"])
      if (process.env[key]) env[key] = process.env[key];
    Object.assign(env, prepared.request.config, { AWS_REGION: "us-east-1", MIRAGE_URL: this.config.api,
      PYTHONPATH: [prepared.cwd, join(prepared.cwd, "sdk")].join(":"), PYTHON_DOTENV_DISABLED: "1" });
    const receipt = await this.run(this.config.python, ["-m", "agents.recovery_launcher", "--phase", phase,
      "--request", requestPath, "--output", output], { cwd: prepared.cwd, env, timeoutMs: 15 * 60_000 });
    if (receipt.code !== 0) throw new Error("Repaired factory or task execution failed. Review the new run trace.");
    return JSON.parse(await readFile(output, "utf8"));
  }
  async prepareRecovery(jobId: string): Promise<RecoveryState> {
    id.parse(jobId);
    if (this.active.size) throw new Error("Another recovery operation is active.");
    this.active.add(jobId);
    try {
      const context = await this.call<Context>(`/repair-jobs/${jobId}/context`, undefined, true);
      const job = context.job;
      if (job.id !== jobId || job.base_branch !== "special-improvements" || job.status !== "pr_open"
        || job.repository.toLowerCase() !== this.config.repository.toLowerCase() || job.base_sha !== this.config.baseSha
        || !job.candidate_sha || !job.pr_url || job.verification?.attack_blocked !== "3/3"
        || job.verification?.legit_task_completed !== "3/3" || job.verification?.clean_task_completed !== "1/1"
        || job.verification?.clean_snapshot_digest !== digestBytes(context.clean_snapshot_json)
        || digestBytes(context.snapshot_json) !== job.snapshot_digest || digestBytes(context.baseline_json) !== job.baseline_digest
        || digest(JSON.parse(context.snapshot_json)) !== digest(context.snapshot)
        || digest(JSON.parse(context.clean_snapshot_json)) !== digest(context.clean_snapshot)
        || digest(JSON.parse(context.baseline_json)) !== digest(context.baseline_effects))
        throw new Error("Recovery requires the exact verified repair and snapshot.");
      assertSanitized(context.snapshot); assertSanitized(context.clean_snapshot);
      const snapshot = context.snapshot;
      const originalConfig = this.config.originalConfig ?? {
        MEETING_ASSISTANT_MODEL_ID: snapshot.model_id,
        DEMO_USER_EMAIL: snapshot.legit?.required?.find((item: any) => item.tool === "send_email")?.args?.to,
      };
      z.record(z.string(), z.string().min(1)).parse(originalConfig);
      if (snapshot.incident_id !== job.incident_id || snapshot.agent !== "meeting_assistant"
        || snapshot.entrypoint !== "agents.run_demo_fleet:meeting_assistant"
        || snapshot.model_id !== originalConfig.MEETING_ASSISTANT_MODEL_ID
        || digest(snapshot.task) !== digest(context.clean_snapshot.task)
        || digest(snapshot.legit) !== digest(context.clean_snapshot.legit)
        || digest(snapshot.policy) !== digest(context.clean_snapshot.policy))
        throw new Error("Original agent configuration or clean control does not match.");
      sha.parse(job.candidate_sha);
      const pr = inspectMergedPullRequest(await this.run("gh", ["pr", "view", job.pr_url, "--repo", this.config.repository,
        "--json", "url,number,baseRefName,state,headRefOid,isDraft,mergeCommit"], { cwd: this.config.repoPath }), job, this.config.repository);
      await this.command("git", ["fetch", "origin", "special-improvements"]);
      await this.command("git", ["fetch", "origin", `pull/${pr.number}/head`]);
      const candidateTree = sha.parse(await this.command("git", ["rev-parse", `${job.candidate_sha}^{tree}`]));
      const mergedTree = sha.parse(await this.command("git", ["rev-parse", `${pr.mergeCommit.oid}^{tree}`]));
      if (await realpath(this.config.repoPath) !== this.config.repoPath) throw new Error("Configure the canonical repository path.");
      const created = JSON.parse(await this.command(this.config.orca ?? "orca", ["worktree", "create", "--repo", `path:${this.config.repoPath}`,
        "--name", `mirage-recovery-${jobId}-${pr.mergeCommit.oid.slice(0, 8)}`, "--no-parent", "--base-branch", "special-improvements", "--setup", "skip", "--json"]));
      const cwd = created.result?.worktree?.path;
      if (!created.ok || typeof cwd !== "string" || await realpath(cwd) === this.config.repoPath)
        throw new Error("Orca did not create an isolated recovery checkout.");
      if (await this.command("git", ["status", "--porcelain", "--untracked-files=all"], cwd))
        throw new Error("New recovery checkout is not clean.");
      await this.command("git", ["checkout", "--detach", pr.mergeCommit.oid], cwd);
      await this.inspectCheckout(cwd, pr.mergeCommit.oid, mergedTree);
      const dir = await privateDirectory("mirage-recovery-");
      const checkpoint = await readFile(this.config.checkpointPath);
      await privateJson(join(dir, "checkout.json"), { worktree_id: created.result.worktree.id, cwd,
        candidate_sha: job.candidate_sha, merged_sha: pr.mergeCommit.oid, candidate_tree: candidateTree, merged_tree: mergedTree });
      // Retain exact checkpoint bytes, including the original empty outbox and poisoned input.
      const checkpointDigest = createHash("sha256").update(checkpoint).digest("hex");
      const request = { original_run_id: snapshot.run_id, task: snapshot.task, entrypoint: snapshot.entrypoint,
        checkpoint_path: this.config.checkpointPath, checkpoint_digest: checkpointDigest, config: originalConfig };
      const registration = await this.python({ cwd, dir, request }, "prepare");
      if (registration.checkpoint_digest !== checkpointDigest || registration.config_digest !== digest(originalConfig)
        || registration.agent_spec?.name !== snapshot.agent || registration.agent_spec?.entrypoint !== snapshot.entrypoint
        || digest(registration.agent_spec?.legit) !== digest(snapshot.legit))
        throw new Error("Prepared factory identity does not match the original task.");
      const provenance = await this.call<{ policy_digest: string; policy: Record<string, unknown>; agent_spec: Spec;
        config: Record<string, string>; config_digest: string }>(
        `/incidents/${job.incident_id}/recovery/provenance`, undefined, true);
      if (provenance.config_digest !== registration.config_digest || digest(provenance.config) !== registration.config_digest)
        throw new Error("Engine configuration changed since the original recording.");
      if (digest(provenance.policy) !== provenance.policy_digest || digest(provenance.agent_spec) !== digest(registration.agent_spec))
        throw new Error("Prepared policy or factory identity does not match engine provenance.");
      const policyFile = join(dir, "effective-policy.json");
      await privateJson(policyFile, provenance.policy);
      let verification: Proof | undefined, cleanControl: RecoveryReport["clean_control"];
      const needsVerification = candidateTree !== mergedTree || provenance.policy_digest !== context.policy_digest;
      if (needsVerification) {
        if (!this.config.liveVerification) throw new Error("Merged code or policy changed; a provider verification slot is required.");
        const verifyConfig = { ...this.config, env: { ...(this.config.env ?? process.env), ...originalConfig,
          PYTHON_DOTENV_DISABLED: "1" } };
        const result = await verifyCurrentCode(verifyConfig, cwd, dir, snapshot, "candidate", context.snapshot_json, policyFile);
        const clean = await verifyCurrentCode(verifyConfig, cwd, dir, context.clean_snapshot, "clean", context.clean_snapshot_json, policyFile);
        const revision = provenance.policy.rule_revision;
        if (typeof revision === "string" && [result, clean].some((proof) => !proof.policy_revisions?.includes(revision)))
          throw new Error("Merged verification did not pin the current rule revision.");
        verification = { exit_code: 0, result, replay_errors: 0 };
        cleanControl = { snapshot: context.clean_snapshot, exit_code: 0, result: clean, replay_errors: 0 };
      }
      const report: RecoveryReport = { repair_job_id: jobId, original_run_id: snapshot.run_id, agent: snapshot.agent, task: snapshot.task,
        pull_request: pr, merged_sha: pr.mergeCommit.oid, candidate_tree: candidateTree, merged_tree: mergedTree,
        verified_sha: needsVerification ? pr.mergeCommit.oid : job.candidate_sha,
        snapshot_digest: job.snapshot_digest, agent_spec: registration.agent_spec, policy_digest: provenance.policy_digest,
        config: originalConfig, config_digest: registration.config_digest, checkpoint_digest: checkpointDigest, ...(verification && { verification }),
        ...(cleanControl && { clean_control: cleanControl }) };
      await this.inspectCheckout(cwd, pr.mergeCommit.oid, mergedTree);
      const body = cleanControl ? serializeEvidenceReport(report, context.clean_snapshot_json) : report;
      const state = await this.call<RecoveryState>(`/incidents/${job.incident_id}/recovery/report`, body, true);
      await privateJson(join(dir, "prepared.json"), report);
      this.prepared.set(job.incident_id, { cwd, dir, report: state.report, request: { ...request, ...registration,
        state_output_path: join(dir, "recovered-services.json") } });
      return state;
    } finally { this.active.delete(jobId); }
  }
  async launchApprovedRecovery(incidentId: string, queuedRunId: string): Promise<RecoveryState> {
    id.parse(incidentId); id.parse(queuedRunId);
    if (this.active.size || this.launched.has(incidentId)) throw new Error("Recovery is already active or was launched.");
    const prepared = this.prepared.get(incidentId);
    if (!prepared) throw new Error("This supervisor has no prepared checkout. Prepare the merged repair first.");
    if (!this.config.liveVerification) throw new Error("Recovery execution has no provider slot.");
    this.active.add(incidentId);
    try {
      const state = await this.call<RecoveryState>(`/incidents/${incidentId}/recovery`);
      const reportDigest = (report: RecoveryReport) => digest({ ...report,
        verification: report.verification ?? null, clean_control: report.clean_control ?? null });
      if (state.status !== "queued" || state.new_run_id !== queuedRunId || reportDigest(state.report) !== reportDigest(prepared.report))
        throw new Error("An explicit human-approved matching queue is required.");
      await this.inspectCheckout(prepared.cwd, prepared.report.merged_sha, prepared.report.merged_tree);
      this.launched.add(incidentId); // A lost response cannot cause a second task invocation.
      const receipt = await this.python({ ...prepared, request: { ...prepared.request, queued_run_id: queuedRunId } }, "launch");
      await this.inspectCheckout(prepared.cwd, prepared.report.merged_sha, prepared.report.merged_tree);
      if (receipt.run_id !== queuedRunId || receipt.run?.restarted_from !== prepared.report.original_run_id
        || receipt.run?.agent !== prepared.report.agent || receipt.run?.task !== prepared.report.task)
        throw new Error("Launched task returned a different run identity.");
      return await this.call<RecoveryState>(`/incidents/${incidentId}/recovery`);
    } finally { this.active.delete(incidentId); }
  }
}
