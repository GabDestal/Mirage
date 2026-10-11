#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createServer } from "./server.js";
import { repairConfig, RepairSupervisor } from "./repair-supervisor.js";
import { recoveryConfig, RecoverySupervisor } from "./recovery.js";

const repair = repairConfig();
const recovery = repair && await recoveryConfig(repair);
await createServer({ ...(repair && { repair: new RepairSupervisor(repair) }),
  ...(recovery && { recovery: new RecoverySupervisor(recovery) }) }).connect(new StdioServerTransport());
