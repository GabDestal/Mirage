import { expect, test, vi } from "vitest";

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
import { createBedrockProvider, publicError } from "../src/bedrock.js";

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
  expect(capture.configs.at(-1).maxAttempts).toBe(1);
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
