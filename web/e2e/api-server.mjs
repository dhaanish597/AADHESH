// Boots the real local Aadesh JSON API for the browser tests.
//
// Playwright's `webServer` spawns this with Node, which keeps the launch cross-platform: we
// pick the repo's own virtualenv interpreter rather than relying on whatever `python` a shell
// happens to resolve. No test doubles are involved -- this is `aadesh_web.server`, the same
// process `make api` runs, so the browser is talking to the real resolver, token service,
// Cedar authorizer and consent store.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");

const candidates = [
  path.join(repoRoot, ".venv", "Scripts", "python.exe"),
  path.join(repoRoot, ".venv", "bin", "python"),
];
const python = candidates.find((p) => existsSync(p)) ?? "python";

const port = process.env.AADESH_API_PORT ?? "8787";
const child = spawn(python, ["-m", "aadesh_web.server", "--port", port], {
  cwd: repoRoot,
  env: { ...process.env, PYTHONPATH: "services" },
  stdio: "inherit",
});

const shutdown = () => child.kill();
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
process.on("exit", shutdown);
child.on("exit", (code) => process.exit(code ?? 0));
