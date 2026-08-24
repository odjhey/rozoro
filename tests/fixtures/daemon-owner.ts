import { mkdir, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { join } from "node:path";

const [home, output] = process.argv.slice(2);
await mkdir(home, {recursive:true, mode:0o700});
const daemon = spawn("python3", [join(process.cwd(), "bin/rozorod.py"), "--home", home], {stdio:"ignore"});
let cleaning = false;
const cleanup = async (signal: "SIGINT"|"SIGTERM") => {
  if (cleaning) return; cleaning = true;
  if (daemon.exitCode === null) {
    daemon.kill("SIGTERM");
    await new Promise<void>((resolve) => daemon.once("exit", () => resolve()));
  }
  const { rm } = await import("node:fs/promises"); await rm(home, {recursive:true, force:true});
  process.kill(process.pid, signal);
};
process.once("SIGINT", () => void cleanup("SIGINT"));
process.once("SIGTERM", () => void cleanup("SIGTERM"));
while (true) {
  try { const { lstat } = await import("node:fs/promises"); if ((await lstat(join(home,"monitor.sock"))).isSocket()) break; } catch {}
  await new Promise((resolve) => setTimeout(resolve, 10));
}
await writeFile(output, home);
await new Promise(() => {});
