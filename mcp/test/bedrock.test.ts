import { afterEach, expect, test, vi } from "vitest";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

vi.mock("node:fs", async (original) => {
  const actual = await original<typeof import("node:fs")>();
  return { ...actual, existsSync: vi.fn(actual.existsSync) };
});

const capture = vi.hoisted(() => ({ requests: [] as any[], configs: [] as any[] }));
// Run the official SDK's endpoint, auth, serializer and retry middleware; replace only HTTP.
vi.mock("@aws-sdk/client-bedrock-runtime", async (original) => {
  const actual = await original<any>();
  return { ...actual, BedrockRuntimeClient: class extends actual.BedrockRuntimeClient {
    constructor(config: any) {
      capture.configs.push(config);
      super({ ...config, credentials: async () => { throw new Error("SigV4 must never be selected"); },
        requestHandler: { async handle(request: any) {
          capture.requests.push(request);
          throw Object.assign(new Error("Synthetic transport stop"), { name: "SyntheticTransportStop" });
        } } });
    }
  } };
});
import { createBedrockProvider, loadChatEnv, publicError } from "../src/bedrock.js";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });

test("official SDK signs bearer in us-east-1, uses env-selected model, sends ConverseStream tools and never retries", async () => {
  capture.requests.length = 0;
  const provider = createBedrockProvider({ AWS_REGION: "us-east-1", AWS_BEARER_TOKEN_BEDROCK: "synthetic-key", BEDROCK_CHAT_MODEL_ID: "configured-chat-profile", BEDROCK_AGENT_MODEL_ID: "ignored-agent-profile" });
  await expect(provider.stream([{ role: "user", content: [{ text: "Hello" }] }], [{ toolSpec: { name: "list_runs", inputSchema: { json: { type: "object", properties: {} } } } }], AbortSignal.timeout(1000))).rejects.toMatchObject({ name: "SyntheticTransportStop" });
  expect(capture.requests).toHaveLength(1);
  expect(capture.requests[0].hostname).toBe("bedrock-runtime.us-east-1.amazonaws.com");
  expect(capture.requests[0].path).toContain("configured-chat-profile/converse-stream");
  expect(capture.requests[0].headers.Authorization).toBe("Bearer synthetic-key");
  const body = JSON.parse(capture.requests[0].body);
  expect(body.toolConfig.tools[0].toolSpec.name).toBe("list_runs");
  expect(body.inferenceConfig).not.toHaveProperty("temperature");
  expect(body.system[0].text).not.toContain("recorded demo background");
  expect(capture.configs.at(-1).maxAttempts).toBe(1);
});

test("demo uses the real SDK with recorded-engine context; live and default systems stay identical", async () => {
  const systems: string[] = [];
  for (const mode of [undefined, "live", "demo"]) {
    const provider = createBedrockProvider({ AWS_BEARER_TOKEN_BEDROCK: "synthetic-key", BEDROCK_CHAT_MODEL_ID: "configured-chat-profile", MIRAGE_UI_MODE: mode });
    await expect(provider.stream([{ role: "user", content: [{ text: "What happened?" }] }], [], AbortSignal.timeout(1000))).rejects.toMatchObject({ name: "SyntheticTransportStop" });
    systems.push(JSON.parse(capture.requests.at(-1).body).system[0].text);
  }
  expect(systems[0]).toBe(systems[1]);
  expect(systems[2]).toContain(systems[0]);
  expect(systems[2]).toContain("Use actual tools to inspect and control the recording");
  expect(systems[2]).toContain("Never claim fresh live detection");
  expect(systems[2]).toContain("real verified fix");
  expect(systems[2]).toContain("same human approvals and audit controls");
  expect(systems[2]).toContain("Do not request or repeat");
  expect(() => createBedrockProvider({ MIRAGE_UI_MODE: "demo" })).toThrow("Set AWS_BEARER_TOKEN_BEDROCK");
});

test("selected absolute env file supplies defaults while shell routing and profile retain precedence", () => {
  const dir = mkdtempSync(join(tmpdir(), "mirage-chat-env-"));
  const path = join(dir, ".env");
  try {
    writeFileSync(path, "MIRAGE_API=http://127.0.0.1:8000\nMIRAGE_UI_MODE=live\nMIRAGE_CHAT_PORT=8001\nMIRAGE_CHAT_ORIGINS=http://localhost:5173\nBEDROCK_CHAT_MODEL_ID=synthetic-configured-model\n");
    vi.stubEnv("MIRAGE_CHAT_ENV_FILE", path);
    vi.stubEnv("MIRAGE_API", "http://127.0.0.1:8010");
    vi.stubEnv("MIRAGE_UI_MODE", "demo");
    vi.stubEnv("MIRAGE_CHAT_PORT", "8011");
    vi.stubEnv("MIRAGE_CHAT_ORIGINS", "http://localhost:5174");
    vi.stubEnv("BEDROCK_CHAT_MODEL_ID", undefined);
    loadChatEnv();
    expect(process.env.MIRAGE_API).toBe("http://127.0.0.1:8010");
    expect(process.env.MIRAGE_UI_MODE).toBe("demo");
    expect(process.env.MIRAGE_CHAT_PORT).toBe("8011");
    expect(process.env.MIRAGE_CHAT_ORIGINS).toBe("http://localhost:5174");
    expect(process.env.BEDROCK_CHAT_MODEL_ID).toBe("synthetic-configured-model");
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("default env path stays repository-local and invalid selected paths fail closed", () => {
  vi.stubEnv("MIRAGE_CHAT_ENV_FILE", undefined);
  vi.mocked(existsSync).mockReturnValue(true);
  const load = vi.spyOn(process, "loadEnvFile").mockImplementation(() => {});
  loadChatEnv();
  expect(load).toHaveBeenCalledWith(fileURLToPath(new URL("../../.env", import.meta.url)));
  vi.stubEnv("MIRAGE_CHAT_ENV_FILE", "relative.env");
  expect(loadChatEnv).toThrow("must be an absolute path");
  vi.mocked(existsSync).mockReturnValue(false);
  vi.stubEnv("MIRAGE_CHAT_ENV_FILE", "/missing/synthetic.env");
  expect(loadChatEnv).toThrow("does not exist");
  expect(load).toHaveBeenCalledTimes(1);
});

test.each(["BEDROCK_AGENT_MODEL_ID", "BEDROCK_MODEL_ID"])("model fallback uses existing %s without a hardcoded ID", async (field) => {
  const provider = createBedrockProvider({ AWS_BEARER_TOKEN_BEDROCK: "synthetic-key", [field]: "configured-fallback" });
  await provider.stream([{ role: "user", content: [{ text: "Hello" }] }], [], AbortSignal.timeout(1000)).catch(() => {});
  expect(capture.requests.at(-1).path).toContain("configured-fallback/converse-stream");
});

test("missing configuration and wrong region fail before creating a client; errors do not echo provider secrets", () => {
  expect(() => createBedrockProvider({})).toThrow("Set AWS_BEARER_TOKEN_BEDROCK");
  expect(() => createBedrockProvider({ AWS_REGION: "eu-west-1" })).toThrow("AWS_REGION=us-east-1");
  expect(publicError(Object.assign(new Error("Bearer synthetic-key"), { name: "ValidationException" })).message).not.toContain("synthetic-key");
});
