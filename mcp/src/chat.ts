import { createServer as createHttpServer } from "node:http";
import type { IncomingMessage, ServerResponse } from "node:http";
import { randomUUID } from "node:crypto";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { ElicitRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import type { CallToolResult, ElicitResult, Tool as McpTool } from "@modelcontextprotocol/sdk/types.js";
import type { ContentBlock, Message, Tool } from "@aws-sdk/client-bedrock-runtime";
import { z } from "zod";
import { createServer, untrusted } from "./server.js";
import type { Options as McpOptions } from "./server.js";
import { ChatError, publicError } from "./bedrock.js";
import type { ModelProvider } from "./bedrock.js";

export const LIMITS = {
  bodyBytes: 16_384, inputChars: 8_000, sessions: 32, activeTurns: 4,
  historyBytes: 65_536, historyMessages: 40, sessionMs: 30 * 60_000,
  rounds: 6, toolCalls: 12, toolMs: 185_000, modelMs: 60_000,
  approvalMs: 120_000, turnMs: 10 * 60_000, resultBytes: 65_536, outputBytes: 32_768,
};
const id = z.string().uuid();
const turnInput = z.object({ session_id: id.optional(), message: z.string().trim().min(1).max(LIMITS.inputChars),
  actor: z.string().trim().min(1).max(80).regex(/^[\p{L}\p{N} ._@-]+$/u) }).strict();
const approvalInput = z.object({ action: z.enum(["accept", "decline"]), content: z.record(z.string(), z.unknown()).optional() }).strict();

export type ChatEvent =
  | { type: "session"; session_id: string }
  | { type: "text_delta"; text: string }
  | { type: "tool_start"; call_id: string; tool: string; args: Record<string, unknown> }
  | { type: "tool_progress"; call_id: string; message: string }
  | { type: "tool_result"; call_id: string; tool: string; result: CallToolResult }
  | { type: "approval_required"; approval_id: string; call_id: string; message: string; schema: Record<string, unknown> }
  | { type: "done" }
  | { type: "error"; code: string; message: string };

type Session = { actor: string; turns: Message[][]; touched: number; busy: boolean; secrets: Set<string> };
type Approval = { session: Session; signal: AbortSignal; settle: (answer: ElicitResult) => void };
type Handoff = { session: Session; prompt: string };
type Emit = (event: ChatEvent) => void;
type ChatOptions = { provider: ModelProvider; mcp?: McpOptions; origins?: string[] };
const errorResult = (message: string): CallToolResult => ({ content: [{ type: "text", text: message }], isError: true });
const tokenKey = /^(?:.*_token|token|authorization|api_key|password)$/i;

function collectTokens(value: unknown, secrets: Set<string>) {
  if (!value || typeof value !== "object") return;
  for (const [key, item] of Object.entries(value)) {
    if (tokenKey.test(key) && typeof item === "string" && item.length) secrets.add(item);
    else collectTokens(item, secrets);
  }
}

function sanitize<T>(value: T, secrets: Set<string>): T {
  const clean = (item: unknown): unknown => {
    if (typeof item === "string") {
      for (const secret of secrets) {
        item = (item as string).split(secret).join("[redacted]").split(encodeURIComponent(secret)).join("[redacted]");
      }
      return (item as string).replace(/Bearer\s+[A-Za-z0-9._~+/-]+=*/gi, "Bearer [redacted]");
    }
    if (Array.isArray(item)) return item.map(clean);
    if (item && typeof item === "object") return Object.fromEntries(Object.entries(item)
      .filter(([key]) => key !== "_meta").map(([key, val]) => [key, tokenKey.test(key) ? "[redacted]" : clean(val)]));
    return item;
  };
  return clean(value) as T;
}

/** Only completed turn groups are retained, so trimming cannot orphan a Bedrock tool result. */
function remember(session: Session, turn: Message[]) {
  session.turns.push(turn);
  while (session.turns.length && (Buffer.byteLength(JSON.stringify(session.turns)) > LIMITS.historyBytes ||
    session.turns.flat().length > LIMITS.historyMessages)) session.turns.shift();
  session.touched = Date.now();
}

async function readJson(req: IncomingMessage) {
  if (req.headers["content-type"]?.split(";")[0].trim().toLowerCase() !== "application/json")
    throw new ChatError("JSON_REQUIRED", "Use Content-Type: application/json.", 415);
  let bytes = 0;
  const chunks: Buffer[] = [];
  for await (const chunk of req.iterator({ destroyOnReturn: false })) {
    bytes += Buffer.byteLength(chunk);
    if (bytes > LIMITS.bodyBytes) throw new ChatError("BODY_TOO_LARGE", "Request body exceeds 16 KiB.", 413);
    chunks.push(Buffer.from(chunk));
  }
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8")); }
  catch { throw new ChatError("INVALID_JSON", "Request body must be valid JSON."); }
}

export function createChatService(opts: ChatOptions) {
  const sessions = new Map<string, Session>();
  const approvals = new Map<string, Approval>();
  const handoffs = new Map<string, Handoff>();
  const controllers = new Set<AbortController>();
  const origins = new Set(opts.origins ?? ["http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:8001", "http://127.0.0.1:8001"]);

  function expire() {
    for (const [key, session] of sessions)
      if (!session.busy && Date.now() - session.touched > LIMITS.sessionMs) sessions.delete(key);
    const alive = new Set(sessions.values());
    for (const [key, handoff] of handoffs) if (!alive.has(handoff.session)) handoffs.delete(key);
  }

  function approval(session: Session, signal: AbortSignal, callId: string, params: { message: string; requestedSchema: object }, emit: Emit) {
    signal.throwIfAborted();
    return new Promise<ElicitResult>((resolve) => {
      const approvalId = randomUUID();
      const settle = (answer: ElicitResult) => {
        clearTimeout(timer);
        signal.removeEventListener("abort", decline);
        approvals.delete(approvalId);
        resolve(answer);
      };
      const decline = () => settle({ action: "decline" });
      const timer = setTimeout(decline, LIMITS.approvalMs);
      approvals.set(approvalId, { session, signal, settle });
      signal.addEventListener("abort", decline, { once: true });
      emit({ type: "approval_required", approval_id: approvalId, call_id: callId,
        message: sanitize(params.message, session.secrets), schema: sanitize(params.requestedSchema as Record<string, unknown>, session.secrets) });
    });
  }

  async function runTurn(session: Session, message: string, signal: AbortSignal, emit: Emit) {
    let callId = "";
    let callSignal = signal;
    const boundedFetch: typeof fetch = (url, init) => {
      callSignal.throwIfAborted();
      return (opts.mcp?.fetch ?? fetch)(url, { ...init,
        signal: AbortSignal.any([callSignal, AbortSignal.timeout(15_000)]) });
    };
    const server = createServer({ ...opts.mcp, actor: session.actor, fetch: boundedFetch });
    const client = new Client({ name: "Mirage Chat", version: "0.1.0" }, { capabilities: { elicitation: { form: {} } } });
    client.setRequestHandler(ElicitRequestSchema, async (request) => {
      if (request.params.mode === "url" || !callId || callSignal.aborted) return { action: "decline" };
      return approval(session, callSignal, callId, request.params, emit);
    });
    const [a, b] = InMemoryTransport.createLinkedPair();
    const turn: Message[] = [{ role: "user", content: [{ text: sanitize(message, session.secrets) }] }];
    let pendingAssistant = false;
    let toolCalls = 0;
    const attempted = new Set<string>();
    try {
      await Promise.all([server.connect(a), client.connect(b)]);
      const catalogue = (await client.listTools(undefined, { signal })).tools;
      const tools: Tool[] = catalogue.map((t) => ({ toolSpec: { name: t.name, description: t.description,
        inputSchema: { json: t.inputSchema as any } } }));
      for (let round = 0; round < LIMITS.rounds; round++) {
        signal.throwIfAborted();
        const modelSignal = AbortSignal.any([signal, AbortSignal.timeout(LIMITS.modelMs)]);
        const history = [...session.turns];
        while (history.length && (Buffer.byteLength(JSON.stringify([...history.flat(), ...turn])) > LIMITS.historyBytes ||
          history.flat().length + turn.length > LIMITS.historyMessages)) history.shift();
        const messages = [...history.flat(), ...turn];
        if (Buffer.byteLength(JSON.stringify(messages)) > LIMITS.historyBytes || messages.length > LIMITS.historyMessages)
          throw new ChatError("CONTEXT_LIMIT", "This turn reached the chat context limit. Inspect the incident dashboard for full details.");
        const reply = await modelReply(opts.provider, messages, tools, modelSignal,
          (text) => emit({ type: "text_delta", text: sanitize(text, session.secrets) }));
        turn.push(sanitize(reply.message, session.secrets));
        const calls = reply.calls;
        if (!calls.length) { remember(session, turn); emit({ type: "done" }); return; }
        pendingAssistant = true;
        const results: ContentBlock[] = [];
        for (const call of calls) {
          signal.throwIfAborted();
          if (++toolCalls > LIMITS.toolCalls) throw new ChatError("TOOL_LIMIT", "This turn reached the tool-call limit. Check current status before continuing.");
          callId = randomUUID();
          emit({ type: "tool_start", call_id: callId, tool: call.name, args: sanitize(call.input, session.secrets) });
          const spec = catalogue.find((t) => t.name === call.name);
          const key = `${call.name}:${String(call.input.run_id ?? call.input.incident_id ?? "")}`;
          const effect = !["list_runs", "get_incident", "get_audit"].includes(call.name);
          let result: CallToolResult;
          if (call.malformed || !validArgs(call.input, spec)) result = errorResult("Tool arguments were rejected. No action was started.");
          else if (effect && attempted.has(key)) result = errorResult("This action was already attempted in this turn. It was not retried; check status.");
          else {
            if (effect) attempted.add(key);
            const toolSignal = AbortSignal.any([signal, AbortSignal.timeout(LIMITS.toolMs)]);
            callSignal = toolSignal;
            try {
              result = await client.callTool({ name: call.name, arguments: call.input }, undefined, {
                signal: toolSignal, timeout: LIMITS.toolMs, maxTotalTimeout: LIMITS.toolMs,
                onprogress: (p) => emit({ type: "tool_progress", call_id: callId, message: sanitize(p.message ?? "Working in Mirage", session.secrets) }),
              }) as CallToolResult;
            } catch {
              signal.throwIfAborted();
              toolSignal.throwIfAborted();
              result = errorResult("The tool call failed or timed out. Already-started actions may continue. Check status; no automatic retry was made.");
            }
          }
          collectTokens(result, session.secrets);
          const modelResult = sanitize(result, session.secrets);
          let uiResult = modelResult;
          if (call.name === "send_fix" && !result.isError) {
            const prompt = result.structuredContent?.prompt;
            let handoffUrl: string | undefined;
            if (typeof prompt === "string" && Buffer.byteLength(prompt) <= LIMITS.resultBytes) {
              // shortcut: keep at most eight handoffs per session; add durable storage only beyond the loopback demo.
              const owned = [...handoffs].filter(([, h]) => h.session === session);
              if (owned.length >= 8) handoffs.delete(owned[0][0]);
              const handoffId = randomUUID();
              handoffs.set(handoffId, { session, prompt });
              handoffUrl = `/chat/handoffs/${handoffId}`;
            }
            modelResult.content = [{ type: "text", text: handoffUrl
              ? "Handoff created. The UI offers the full prompt to the human. A human must merge any resulting PR and approve a clean restart."
              : "Handoff was created in the engine, but its prompt is missing or exceeds the chat limit. Retrieve it from the incident dashboard; do not repeat this action." }];
            if (!handoffUrl) modelResult.isError = true;
            modelResult.structuredContent = {};
            const url = result.structuredContent?.codex_url;
            const codexUrl = url === "https://chatgpt.com/codex" ? url : undefined;
            uiResult = { ...modelResult, structuredContent: { ...(handoffUrl && { handoff_url: handoffUrl }), ...(codexUrl && { codex_url: codexUrl }) } };
          }
          if (Buffer.byteLength(JSON.stringify(uiResult)) > LIMITS.resultBytes) uiResult = errorResult("Tool response exceeded the chat display limit. Check the incident dashboard for details.");
          emit({ type: "tool_result", call_id: callId, tool: call.name, result: uiResult });
          const modelText = Buffer.byteLength(JSON.stringify(modelResult)) <= LIMITS.resultBytes
            ? untrusted("mcp_tool_result", modelResult) : "Tool result too large; check the dashboard. Do not repeat an action.";
          results.push({ toolResult: { toolUseId: call.id, content: [{ text: modelText }], status: modelResult.isError ? "error" : "success" } });
          callId = "";
          callSignal = signal;
        }
        turn.push({ role: "user", content: results });
        pendingAssistant = false;
      }
      throw new ChatError("ROUND_LIMIT", "This turn reached the model-round limit. Check current status before continuing.");
    } catch (error) {
      if (pendingAssistant) turn.pop();
      turn.push({ role: "assistant", content: [{ text: "This chat turn stopped before completion. Already-started engine actions may continue. Inspect current status before starting another action." }] });
      remember(session, turn);
      throw error;
    } finally {
      await Promise.allSettled([client.close(), server.close()]);
    }
  }

  const http = createHttpServer(async (req, res) => {
    try {
      const host = new URL(`http://${req.headers.host ?? ""}`).hostname;
      if (!["localhost", "127.0.0.1", "[::1]"].includes(host)) throw new ChatError("ORIGIN_REJECTED", "Loopback host required.", 403);
      if (req.headers.origin && !origins.has(req.headers.origin)) throw new ChatError("ORIGIN_REJECTED", "This browser origin is not allowed.", 403);
      if (req.headers["sec-fetch-site"] === "cross-site") throw new ChatError("ORIGIN_REJECTED", "Cross-site requests are not allowed.", 403);
      expire();
      const path = new URL(req.url ?? "/", "http://localhost").pathname;
      if (req.method === "GET" && path.startsWith("/chat/handoffs/")) {
        const handoff = handoffs.get(path.slice("/chat/handoffs/".length));
        if (!handoff) throw new ChatError("HANDOFF_EXPIRED", "This handoff is unavailable or its session expired.", 404);
        res.writeHead(200, { "content-type": "text/plain; charset=utf-8", "content-disposition": 'attachment; filename="mirage-handoff.txt"',
          "cache-control": "no-store", "x-content-type-options": "nosniff" });
        res.end(handoff.prompt); return;
      }
      if (req.method !== "POST") throw new ChatError("NOT_FOUND", "Chat endpoint not found.", 404);
      const body = await readJson(req);
      if (path.startsWith("/chat/approvals/")) {
        const input = approvalInput.safeParse(body);
        if (!input.success) throw new ChatError("INVALID_APPROVAL", "Approval requires action accept or decline and optional form content.");
        const pending = approvals.get(path.slice("/chat/approvals/".length));
        if (!pending || !pending.session.busy || pending.signal.aborted) throw new ChatError("APPROVAL_STALE", "This approval is expired, already submitted, or disconnected.", 409);
        pending.settle(input.data as ElicitResult);
        json(res, 200, { accepted: true }); return;
      }
      if (path !== "/chat/turn") throw new ChatError("NOT_FOUND", "Chat endpoint not found.", 404);
      const input = turnInput.safeParse(body);
      if (!input.success) throw new ChatError("INVALID_TURN", "Provide message (1–8000 characters), actor (1–80 characters), and an optional server-issued session_id only.");
      const { session_id, actor, message } = input.data;
      let session = session_id ? sessions.get(session_id) : undefined;
      if (session_id && !session) throw new ChatError("SESSION_EXPIRED", "This session is unavailable or expired. Start a new conversation.", 404);
      if (session && session.actor !== actor) throw new ChatError("ACTOR_MISMATCH", "A session belongs to its original actor.", 403);
      if (session?.busy) throw new ChatError("SESSION_BUSY", "This session already has a live turn.", 409);
      if (controllers.size >= LIMITS.activeTurns) throw new ChatError("CHAT_BUSY", "All chat slots are busy. Try again after a turn finishes.", 429);
      if (!session && sessions.size >= LIMITS.sessions) throw new ChatError("SESSION_LIMIT", "The chat session limit was reached. Expired sessions are cleared after 30 minutes.", 429);
      const sessionId = session_id ?? randomUUID();
      if (!session) {
        session = { actor, turns: [], touched: Date.now(), busy: false, secrets: new Set([process.env.AWS_BEARER_TOKEN_BEDROCK ?? ""].filter(Boolean)) };
        sessions.set(sessionId, session);
      }
      session.busy = true;
      session.touched = Date.now();
      const controller = new AbortController();
      controllers.add(controller);
      const timeout = setTimeout(() => controller.abort(new DOMException("Turn timed out", "TimeoutError")), LIMITS.turnMs);
      const disconnect = () => { if (!res.writableEnded) controller.abort(new DOMException("Disconnected", "AbortError")); };
      res.on("close", disconnect);
      res.writeHead(200, { "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache, no-transform",
        connection: "keep-alive", "x-accel-buffering": "no", "x-content-type-options": "nosniff" });
      res.flushHeaders();
      const emit: Emit = (event) => {
        if (controller.signal.aborted || res.destroyed) return;
        if (res.writableLength > LIMITS.resultBytes * 2) { controller.abort(new DOMException("Slow consumer", "AbortError")); res.destroy(); return; }
        res.write(`data: ${JSON.stringify(event)}\n\n`);
      };
      emit({ type: "session", session_id: sessionId });
      const keepalive = setInterval(() => { if (!res.destroyed && !controller.signal.aborted) res.write(": keepalive\n\n"); }, 15_000);
      try { await runTurn(session, message, controller.signal, emit); }
      catch (error) {
        const safe = publicError(controller.signal.aborted ? controller.signal.reason : error);
        if (!res.destroyed) res.write(`data: ${JSON.stringify({ type: "error", code: safe.code, message: safe.message })}\n\n`);
      } finally {
        clearInterval(keepalive); clearTimeout(timeout);
        controller.abort(); controllers.delete(controller);
        res.removeListener("close", disconnect);
        session.busy = false; session.touched = Date.now(); res.end();
      }
    } catch (error) {
      const safe = publicError(error);
      if (!res.headersSent) json(res, safe.status, { type: "error", code: safe.code, message: safe.message });
      else res.end();
    }
  });
  http.requestTimeout = 10_000;
  http.headersTimeout = 10_000;
  http.on("close", () => { for (const controller of controllers) controller.abort(); });
  return { http, close: async () => {
    for (const controller of controllers) controller.abort();
    http.closeAllConnections();
    await new Promise<void>((resolve) => http.close(() => resolve()));
  } };
}

function json(res: ServerResponse, status: number, body: unknown) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store", "x-content-type-options": "nosniff" });
  res.end(JSON.stringify(body));
}

function validArgs(args: Record<string, unknown>, spec?: McpTool) {
  return spec && Object.keys(args).every((key) => Object.hasOwn(spec.inputSchema.properties ?? {}, key));
}

type ModelCall = { id: string; name: string; input: Record<string, unknown>; malformed: boolean };
async function modelReply(provider: ModelProvider, messages: Message[], tools: Tool[], signal: AbortSignal, text: (delta: string) => void) {
  const response = await provider.stream(messages, tools, signal);
  if (!response.stream) throw new ChatError("PROVIDER_STREAM", "Bedrock returned no response stream.", 502);
  const blocks = new Map<number, { text?: string; id?: string; name?: string; raw?: string; stopped?: boolean }>();
  let stop: string | undefined;
  let size = 0;
  for await (const event of response.stream) {
    signal.throwIfAborted();
    size += Buffer.byteLength(JSON.stringify(event));
    if (size > LIMITS.outputBytes) throw new ChatError("OUTPUT_LIMIT", "The model response exceeded the chat limit.", 502);
    for (const key of ["internalServerException", "modelStreamErrorException", "validationException", "throttlingException", "serviceUnavailableException"]) {
      if (key in event) throw Object.assign(new Error("Bedrock stream failed"), { name: key[0].toUpperCase() + key.slice(1) });
    }
    if (event.contentBlockStart) {
      const { contentBlockIndex: index, start } = event.contentBlockStart;
      if (index === undefined || blocks.has(index)) throw new ChatError("PROVIDER_STREAM", "Bedrock returned an invalid content block.", 502);
      const use = start?.toolUse;
      blocks.set(index, use ? { id: use.toolUseId, name: use.name, raw: "" } : {});
    }
    if (event.contentBlockDelta) {
      const { contentBlockIndex: index, delta } = event.contentBlockDelta;
      if (index === undefined) throw new ChatError("PROVIDER_STREAM", "Bedrock returned an invalid delta.", 502);
      const block = blocks.get(index) ?? {};
      if (block.stopped) throw new ChatError("PROVIDER_STREAM", "Bedrock returned a delta after closing its block.", 502);
      if (delta?.text !== undefined) { block.text = (block.text ?? "") + delta.text; text(delta.text); }
      if (delta?.toolUse) {
        if (!block.id || delta.toolUse.input === undefined) throw new ChatError("PROVIDER_STREAM", "Bedrock returned an invalid tool delta.", 502);
        block.raw = (block.raw ?? "") + delta.toolUse.input;
      }
      blocks.set(index, block);
    }
    if (event.contentBlockStop) {
      const block = blocks.get(event.contentBlockStop.contentBlockIndex!);
      if (block) block.stopped = true;
    }
    if (event.messageStop) stop = event.messageStop.stopReason;
  }
  signal.throwIfAborted();
  if (!stop) throw new ChatError("PROVIDER_STREAM", "The Bedrock stream ended before the message completed.", 502);
  const content: ContentBlock[] = [];
  const calls: ModelCall[] = [];
  const ids = new Set<string>();
  for (const [, block] of [...blocks].sort(([a], [b]) => a - b)) {
    if (block.id || block.name) {
      if (!block.stopped || !block.id || !/^[-\w]{1,128}$/.test(block.id) || !block.name || ids.has(block.id))
        throw new ChatError("PROVIDER_STREAM", "Bedrock returned an invalid tool call.", 502);
      ids.add(block.id);
      let input: Record<string, unknown> = {};
      let malformed = false;
      try {
        const parsed = JSON.parse(block.raw ?? "");
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed) || Buffer.byteLength(block.raw ?? "") > 8192) malformed = true;
        else input = parsed;
      } catch { malformed = true; }
      calls.push({ id: block.id, name: block.name, input, malformed });
      content.push({ toolUse: { toolUseId: block.id, name: block.name, input: input as any } });
    } else if (block.text !== undefined) content.push({ text: block.text });
  }
  if (!content.length || calls.length > LIMITS.toolCalls || (calls.length > 0 && stop !== "tool_use") || (stop === "tool_use" && !calls.length))
    throw new ChatError("PROVIDER_STREAM", "Bedrock returned an incomplete or unsupported message.", 502);
  return { message: { role: "assistant", content } as Message, calls };
}
