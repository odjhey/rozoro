import assert from "node:assert/strict";
import { chmod, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { createServer, type Server, type Socket } from "node:net";
import extension from "../../.pi/extensions/rozoro-watchtower.ts";

type Handler = (...args: any[]) => any;
type Listener = { server: Server; sockets: Set<Socket>; connections: number; frames: string[] };
const delay = (ms: number) => new Promise((done) => setTimeout(done, ms));
const waitFor = async (predicate: () => boolean, timeout = 3000) => {
  const deadline = Date.now() + timeout;
  while (!predicate()) { if (Date.now() >= deadline) throw new Error("socket connection timed out"); await delay(10); }
};
async function listen(home: string, serverMode: "normal" | "withhold" | "peer-close" = "normal", readyPath?: string): Promise<Listener> {
  await mkdir(home, { recursive: true, mode: 0o700 }); await chmod(home, 0o700);
  const state: Listener = { server: undefined as unknown as Server, sockets: new Set(), connections: 0, frames: [] };
  state.server = createServer((socket) => {
    state.connections++; state.sockets.add(socket); let buffered = "";
    socket.setEncoding("utf8"); socket.on("error", () => undefined);
    socket.on("data", (chunk) => {
      buffered += chunk;
      for (;;) {
        const newline = buffered.indexOf("\n"); if (newline < 0) break;
        const frame = JSON.parse(buffered.slice(0, newline)); buffered = buffered.slice(newline + 1);
        state.frames.push(frame.type);
        if (frame.type === "session.register" && serverMode !== "normal") void writeFile(readyPath!, `${serverMode}\n`);
        if (serverMode === "peer-close") { socket.destroy(); continue; }
        if (serverMode === "withhold") continue;
        if (["session.register", "turn.start", "turn.stop"].includes(frame.type) && !socket.destroyed && socket.writable)
          socket.write(JSON.stringify({ v: 1, type: "ack", event_id: frame.event_id, durable_seq: frame.producer_seq }) + "\n", () => undefined);
      }
    });
    socket.on("close", () => state.sockets.delete(socket));
  });
  await new Promise<void>((ok, fail) => state.server.listen(join(home, "monitor.sock"), ok).once("error", fail));
  await chmod(join(home, "monitor.sock"), 0o600);
  return state;
}
async function close(listener: Listener) {
  for (const socket of listener.sockets) socket.destroy();
  await new Promise<void>((done) => listener.server.close(() => done()));
}

const cell = process.argv[2];
const mode = process.argv[3] ?? "normal";
const root = process.env.ROZORO_HOME_FIXTURE_ROOT!;
assert.ok(root, "ROZORO_HOME_FIXTURE_ROOT is required");
const initial = join(root, "initial"), later = join(root, "later"), user = join(root, "user");
const publicHome = join(initial, "public"), legacyHome = join(initial, "legacy");
const defaultHome = join(user, ".rozoro"), relativeHome = join(initial, "relative"), tildeHome = join(user, "tilde");
const xdgHome = join(root, "xdg", "rozoro"), deferredRelative = join(later, "relative");
const homes = [publicHome, legacyHome, defaultHome, relativeHome, tildeHome, xdgHome, deferredRelative];
const expected: Record<string, string> = { P: publicHome, L: legacyHome, B: publicHome, E: legacyHome, D: defaultHome, R: relativeHome, T: tildeHome, X: defaultHome };
assert.ok(expected[cell] || cell === "U", `unknown matrix cell ${cell}`);
await mkdir(root, { recursive: true }); await Promise.all([mkdir(initial), mkdir(later), mkdir(user, { recursive: true })]);
const listeners = new Map<string, Listener>();
const oldCwd = process.cwd();
try {
  for (const home of homes) {
    const serverMode = home === expected[cell] && mode === "timeout" ? "withhold" : home === expected[cell] && mode === "peer-close" ? "peer-close" : "normal";
    listeners.set(home, await listen(home, serverMode, join(root, "ready")));
  }
  delete process.env.ROZORO_HOME; delete process.env.RZR_HOME;
  process.env.HOME = user; process.env.XDG_CONFIG_HOME = join(root, "xdg");
  if (cell === "P") process.env.ROZORO_HOME = "public";
  if (cell === "L") process.env.RZR_HOME = "legacy";
  if (cell === "B") { process.env.ROZORO_HOME = "public"; process.env.RZR_HOME = "legacy"; }
  if (cell === "E") { process.env.ROZORO_HOME = ""; process.env.RZR_HOME = "legacy"; }
  if (cell === "R") process.env.ROZORO_HOME = "relative";
  if (cell === "T") process.env.ROZORO_HOME = "~/tilde";
  if (cell === "X") { process.env.ROZORO_HOME = ""; process.env.RZR_HOME = ""; }
  if (cell === "U") process.env.ROZORO_HOME = "~rozoro-no-such-user-h3/home";
  process.chdir(initial);
  const handlers = new Map<string, Handler[]>();
  let releaseInitialization!: () => void;
  const initializationBarrier = new Promise<void>((done) => { releaseInitialization = done; });
  const pi = {
    on(name: string, handler: Handler) { handlers.set(name, [...(handlers.get(name) ?? []), handler]); },
    registerCommand() {}, sendMessage() {},
    async exec() { await initializationBarrier; return { code: 0, stdout: "", stderr: "" }; },
  };
  if (cell === "U") {
    assert.throws(() => extension(pi as any), /unresolved user home path/);
    await delay(30);
    for (const [home, listener] of listeners) assert.equal(listener.connections, 0, `invalid user connected to ${home}`);
    console.log(JSON.stringify({ cell, selected: "N/A", matrixResult: "pass" }));
  } else {
    extension(pi as any); // registration is the point at which relative home must become absolute
    if (cell === "R") process.chdir(later);
    const ctx = { getSystemPrompt: () => "rozoro-task: task-home-matrix", sessionManager: { getSessionId: () => `session-${cell}` }, ui: { setStatus() {}, notify() {} } };
    for (const handler of handlers.get("session_start") ?? []) handler({}, ctx);
    for (const handler of handlers.get("agent_start") ?? []) handler();
    for (const handler of handlers.get("agent_settled") ?? []) handler();
    await delay(20);
    assert.equal([...listeners.values()].reduce((sum, listener) => sum + listener.connections, 0), 0, "initialization barrier leaked a connection");
    releaseInitialization();
    await waitFor(() => listeners.get(expected[cell])!.connections === 1);
    if (mode === "timeout") {
      await waitFor(() => listeners.get(expected[cell])!.frames.includes("session.register"));
      await new Promise(() => undefined); // parent kills only after the real write is observed via ready
    } else if (mode === "peer-close") {
      await waitFor(() => listeners.get(expected[cell])!.connections >= 2, 5000);
      await waitFor(() => listeners.get(expected[cell])!.frames.filter((frame) => frame === "session.register").length >= 2, 5000);
      assert.ok(listeners.get(expected[cell])!.frames.filter((frame) => frame === "session.register").length >= 2, "real client did not write again after peer close");
    } else {
      await waitFor(() => listeners.get(expected[cell])!.frames.includes("turn.stop"));
      assert.deepEqual(listeners.get(expected[cell])!.frames.slice(0, 3), ["session.register", "turn.start", "turn.stop"]);
    }
    if (mode === "normal") assert.equal(listeners.get(expected[cell])!.connections, 1);
    for (const [home, listener] of listeners) if (home !== expected[cell]) assert.equal(listener.connections, 0, `connected to decoy ${home}`);
    if (cell === "X") {
      assert.equal(listeners.get(xdgHome)!.connections, 0, "XDG socket was connected");
      assert.deepEqual(listeners.get(xdgHome)!.frames, [], "XDG socket was written");
    }
    for (const handler of handlers.get("session_shutdown") ?? []) await handler();
    await waitFor(() => listeners.get(expected[cell])!.sockets.size === 0);
    console.log(JSON.stringify({ cell, selected: resolve(expected[cell]), matrixResult: "pass" }));
  }
} finally {
  process.chdir(oldCwd);
  await Promise.allSettled([...listeners.values()].map(close));
  await rm(root, { recursive: true, force: true });
  assert.equal((await readdir(join(root, ".."))).includes(root.split("/").at(-1)!), false);
}
