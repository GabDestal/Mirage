// One read-only provider request. Tool proposals are counted, never executed.
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { createServer } from "../dist/server.js";
import { createBedrockProvider, loadChatEnv, publicError } from "../dist/bedrock.js";

loadChatEnv();
const server = createServer();
const client = new Client({ name: "Mirage Chat Smoke", version: "1" });
const [a, b] = InMemoryTransport.createLinkedPair();
try {
  await Promise.all([server.connect(a), client.connect(b)]);
  const tools = (await client.listTools()).tools.map((t) => ({ toolSpec: {
    name: t.name, description: t.description, inputSchema: { json: t.inputSchema },
  } }));
  const response = await createBedrockProvider().stream([
    { role: "user", content: [{ text: "Say Mirage is ready in one sentence. Do not use tools." }] },
  ], tools, AbortSignal.timeout(60_000));
  let textChars = 0, toolCalls = 0, complete = false;
  if (!response.stream) throw new Error("Missing stream");
  for await (const event of response.stream) {
    const error = Object.keys(event).find((k) => k.endsWith("Exception"));
    if (error) throw Object.assign(new Error("Provider stream error"), { name: error[0].toUpperCase() + error.slice(1) });
    textChars += event.contentBlockDelta?.delta?.text?.length ?? 0;
    if (event.contentBlockStart?.start?.toolUse) toolCalls++;
    if (event.messageStop) complete = true;
  }
  if (!complete || !textChars || toolCalls) throw new Error("Read-only provider smoke did not complete as requested");
  console.log(JSON.stringify({ ok: true, provider: "Bedrock ConverseStream", region: "us-east-1", catalogue: tools.length, textChars, toolCalls }));
} catch (error) {
  const safe = publicError(error);
  console.error(JSON.stringify({ ok: false, code: safe.code, message: safe.message,
    ...(error?.$metadata?.httpStatusCode && { http_status: error.$metadata.httpStatusCode }) }));
  process.exitCode = 1;
} finally {
  await Promise.allSettled([client.close(), server.close()]);
}
