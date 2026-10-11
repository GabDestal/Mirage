#!/usr/bin/env node
import { createBedrockProvider, loadChatEnv, publicError } from "./bedrock.js";
import { createChatService } from "./chat.js";
import { repairConfig, RepairSupervisor } from "./repair-supervisor.js";
import { recoveryConfig, RecoverySupervisor } from "./recovery.js";

try {
  loadChatEnv();
  const port = Number(process.env.MIRAGE_CHAT_PORT ?? 8001);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("Invalid chat port");
  const repair = repairConfig();
  const recovery = repair && await recoveryConfig(repair);
  const launcher = recovery && new RecoverySupervisor(recovery);
  const service = createChatService({ provider: createBedrockProvider(), mcp: { ...(repair && { repair: new RepairSupervisor(repair) }),
    ...(launcher && { recovery: launcher }) }, ...(launcher && { recovery: launcher }),
    ...(process.env.MIRAGE_CHAT_ORIGINS && { origins: process.env.MIRAGE_CHAT_ORIGINS.split(",").map((s) => s.trim()) }) });
  service.http.listen(port, "127.0.0.1", () => console.log(`Mirage chat: http://localhost:${port} (real Bedrock Miragio, ${process.env.MIRAGE_UI_MODE === "demo" ? "recorded engine" : "configured engine"}, us-east-1)`));
  service.http.on("error", () => { console.error("Mirage chat could not bind its loopback port."); process.exitCode = 1; });
  for (const sig of ["SIGINT", "SIGTERM"] as const) process.once(sig, () => { void service.close(); });
} catch (error) {
  const safe = publicError(error);
  console.error(JSON.stringify({ code: safe.code, message: safe.message }));
  process.exitCode = 1;
}
