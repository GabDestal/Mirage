#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createServer } from "./server.js";
import { repairConfig, RepairSupervisor } from "./repair-supervisor.js";

const repair = repairConfig();
await createServer({ ...(repair && { repair: new RepairSupervisor(repair) }) }).connect(new StdioServerTransport());
