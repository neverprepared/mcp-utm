#!/usr/bin/env node

import { execFileSync, spawn } from "node:child_process";

// Resolve uvx — prefer PATH, fall back to common install locations.
function findUvx() {
  const candidates = [
    "uvx",
    `${process.env.HOME}/.local/bin/uvx`,
    "/opt/homebrew/bin/uvx",
    "/usr/local/bin/uvx",
  ];
  for (const c of candidates) {
    try {
      execFileSync(c, ["--version"], { stdio: "ignore" });
      return c;
    } catch {
      continue;
    }
  }
  return null;
}

const uvx = findUvx();
if (!uvx) {
  process.stderr.write(
    "mcp-utm: uvx not found. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh\n"
  );
  process.exit(1);
}

const child = spawn(uvx, ["--from", "mcp-utm", "mcp-utm", ...process.argv.slice(2)], {
  stdio: "inherit",
});

child.on("exit", (code) => process.exit(code ?? 1));
