import assert from "node:assert/strict";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtemp, readdir, rm } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";

const fixture = join(import.meta.dirname, "fixtures", "pi-extension-home-child.ts");
const cells = ["P", "L", "B", "E", "D", "R", "T", "X"] as const; // O: N/A (the extension has no CLI override)
const runtimes = [{ name: "Node", command: process.env.NODE ?? "node" }, { name: "Bun", command: process.env.BUN ?? "bun" }] as const;

type Result = { cell: string; selected: string; matrixResult: "pass" };
async function run(runtime: typeof runtimes[number], cell: string): Promise<Result> {
  const guard = await mkdtemp(join("/tmp", `rpp-${runtime.name[0]}${cell}-`));
  let child: ChildProcess | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const fixtureRoot = join(guard, "root");
    child = spawn(runtime.command, [fixture, cell], { cwd: guard, env: { ...process.env, HOME: join(fixtureRoot, "user"), ROZORO_HOME_FIXTURE_ROOT: fixtureRoot }, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "", stderr = "";
    child.stdout!.on("data", (chunk) => { stdout += chunk; }); child.stderr!.on("data", (chunk) => { stderr += chunk; });
    const code = await new Promise<number | null>((resolve, reject) => {
      timer = setTimeout(() => { child!.kill("SIGKILL"); reject(new Error(`${runtime.name}/${cell} timed out`)); }, 8000);
      child!.once("error", reject); child!.once("exit", resolve);
    });
    assert.equal(code, 0, `${runtime.name}/${cell}: ${stderr || stdout}`);
    const line = stdout.trim().split("\n").at(-1)!; const result = JSON.parse(line) as Result;
    assert.deepEqual({ cell: result.cell, matrixResult: result.matrixResult }, { cell, matrixResult: "pass" });
    return result;
  } finally {
    if (timer) clearTimeout(timer);
    if (child && child.exitCode === null && child.signalCode === null) {
      child.kill("SIGKILL");
      await new Promise((done) => child!.once("exit", done));
    }
    const survived = child?.exitCode === null && child?.signalCode === null;
    let removalError: unknown;
    try { await rm(guard, { recursive: true, force: true }); } catch (error) { removalError = error; }
    const residue = (await readdir(join(guard, ".."))).includes(guard.split("/").at(-1)!);
    assert.equal(survived, false, `${runtime.name}/${cell} child survived`);
    assert.ifError(removalError);
    assert.equal(residue, false, `${runtime.name}/${cell} left socket/temp state`);
  }
}

for (const runtime of runtimes) {
  test(`${runtime.name}: extension socket home matrix P/L/B/E/D/R/T/X plus unresolved user (O=N/A)`, { concurrency: false, timeout: 120_000 }, async () => {
    const matrix: Result[] = [];
    for (const cell of [...cells, "U"] as const) matrix.push(await run(runtime, cell));
    console.log(`matrix-result ${runtime.name} ${matrix.map(({ cell }) => `${cell}=pass`).join(" ")} O=N/A`);
  });
  test(`${runtime.name}: 20x per cell native fresh-process socket-home repetition`, { concurrency: false, timeout: 120_000 }, async () => {
    for (const cell of cells) for (let repetition = 0; repetition < 20; repetition++) await run(runtime, cell);
    console.log(`matrix-result ${runtime.name} ${cells.map((cell) => `${cell}=20/20`).join(" ")}`);
  });
}
