import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { chmod, lstat, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn, type ChildProcess } from "node:child_process";
import { createServer, createConnection, type Server, type Socket } from "node:net";
import test from "node:test";
import { herdrDriverId, MAX_FRAME_BYTES, RozoroEventBusClient, WAKE_CONTENT } from "../.pi/extensions/rozoro-event-bus-client.ts";

const waitFor = async (predicate: () => boolean, timeout = 2000) => {
	const end = Date.now() + timeout;
	while (!predicate()) {
		if (Date.now() > end) throw new Error("timed out");
		await new Promise((resolve) => setTimeout(resolve, 10));
	}
};

async function fakeServer(path: string, frames: Record<string, unknown>[]): Promise<{ server: Server; sockets: Set<Socket> }> {
	const sockets = new Set<Socket>();
	const server = createServer((socket) => {
		sockets.add(socket); socket.setEncoding("utf8");
		let buffer = "";
		socket.on("data", (chunk: string) => {
			buffer += chunk;
			for (;;) {
				const nl = buffer.indexOf("\n"); if (nl < 0) break;
				const frame = JSON.parse(buffer.slice(0, nl)); buffer = buffer.slice(nl + 1); frames.push(frame);
				if (frame.type === "watchtower.register") socket.write(`${JSON.stringify({v:1,type:"ok",request_id:frame.request_id})}\n`);
				else if (["session.register","turn.start","turn.stop"].includes(frame.type)) socket.write(`${JSON.stringify({v:1,type:"ack",event_id:frame.event_id,durable_seq:frames.length})}\n`);
				else if (frame.type === "notification.delivered") socket.write(`${JSON.stringify({v:1,type:"ok",request_id:frame.request_id})}\n`);
			}
		});
		socket.on("close", () => sockets.delete(socket));
	});
	await new Promise<void>((resolve, reject) => server.listen(path, resolve).once("error", reject));
	await chmod(path, 0o600);
	return { server, sockets };
}

const startDaemon = async (home: string): Promise<ChildProcess> => {
	const child = spawn("python3", [join(process.cwd(), "bin/rzr-monitor.py"), "run"], {env:{...process.env,ROZORO_HOME:home},stdio:"ignore"});
	const end = Date.now() + 5000;
	for (;;) {
		try { if ((await lstat(join(home, "monitor.sock"))).isSocket()) break; } catch { /* starting */ }
		if (Date.now() > end) throw new Error("daemon did not start");
		await new Promise((resolve) => setTimeout(resolve, 20));
	}
	return child;
};
const stopDaemon = async (child: ChildProcess) => {
	child.kill("SIGTERM"); await new Promise<void>((resolve) => child.once("exit", () => resolve()));
};
const sendProducer = async (path: string) => {
	const socket = createConnection(path); await new Promise<void>((resolve) => socket.once("connect", resolve));
	socket.write(JSON.stringify({v:1,type:"session.register",event_id:`crew-${randomUUID()}`,producer_seq:1,session_id:"crew-native",harness:"claude",role:"crew",task_id:"task-native"}) + "\n");
	await new Promise<void>((resolve) => socket.once("data", () => resolve())); socket.destroy();
};

const closeServer = async (server: Server, sockets: Set<Socket>) => {
	for (const socket of sockets) socket.destroy();
	await new Promise<void>((resolve) => server.close(() => resolve()));
};

test("native daemon preserves delivered-unacked wake across restart and fixed reconcile identity", async () => {
	const home = await mkdtemp(join(tmpdir(), "rozoro-native-")); const path = join(home, "monitor.sock");
	const driver = herdrDriverId("w7:p12"); const target = join(home, "watchtowers", driver);
	await mkdir(target, {recursive:true,mode:0o700}); await writeFile(join(target, "target.json"), JSON.stringify({schema:1,driver_id:driver,harness:"pi"}) + "\n", {mode:0o600});
	let daemon = await startDaemon(home); await sendProducer(path); const wakes: string[] = [];
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"native-pi-session",driverId:driver,reconnectMs:20,onNotification:()=>{wakes.push(WAKE_CONTENT);}});
	client.start(); await waitFor(() => wakes.length === 1); await stopDaemon(daemon); daemon = await startDaemon(home);
	await waitFor(() => wakes.length === 2, 5000); await new Promise((resolve) => setTimeout(resolve, 100)); assert.equal(wakes.length, 2);
	const reconcile = spawn(join(process.cwd(), "bin/rozoro"), ["reconcile", "--json"], {env:{...process.env,ROZORO_HOME:home,ROZORO_EVENT_BUS:"1",HERDR_PANE_ID:"w7:p12"}});
	let stdout = ""; reconcile.stdout?.on("data", (chunk) => { stdout += chunk; });
	const code = await new Promise<number|null>((resolve) => reconcile.once("exit", resolve)); assert.equal(code, 0); assert.equal(JSON.parse(stdout).driver, driver);
	client.close(); await stopDaemon(daemon); await rm(home, {recursive:true,force:true});
});

test("uses prose-free registration, publishes only certified Pi lifecycle, and confirms after fixed wake", async () => {
	const dir = await mkdtemp(join(tmpdir(), "rozoro-pi-")); const path = join(dir, "monitor.sock");
	const frames: Record<string, unknown>[] = []; const fake = await fakeServer(path, frames); const delivered: string[] = [];
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"pi-session",driverId:"driver-1",
		onNotification: async () => { delivered.push(WAKE_CONTENT); }});
	client.start(); await waitFor(() => frames.some((f) => f.type === "session.register"));
	client.publish("turn.start"); client.publish("turn.stop");
	await waitFor(() => frames.some((f) => f.type === "turn.stop"));
	const socket = [...fake.sockets][0]!;
	socket.write('{"v":1,"type":"notification","generation":7,"priority":"normal","task_count":3}\n');
	await waitFor(() => frames.some((f) => f.type === "notification.delivered"));
	assert.deepEqual(delivered, ["Rozoro notification pending; run ./bin/rozoro reconcile."]);
	assert.equal(frames.find((f) => f.type === "notification.delivered")!.generation, 7);
	assert.equal(frames.find((f) => f.type === "turn.stop")!.background_active, null);
	assert.ok(!frames.some((f) => "content" in f || "message" in f || "reason" in f));
	client.close(); client.close(); await closeServer(fake.server, fake.sockets); await rm(dir, {recursive:true,force:true});
});

test("stable driver identity matches fixed reconcile environment across resume", () => {
	assert.equal(herdrDriverId("w7:p12"), "herdr-w7_p12");
	assert.equal(herdrDriverId("w7:p12"), herdrDriverId("w7:p12"));
});

test("metadata rewrites do not churn the connected adapter epoch", async () => {
	const dir = await mkdtemp(join(tmpdir(), "rozoro-pi-")); const path = join(dir, "monitor.sock");
	const frames: Record<string, unknown>[] = []; const fake = await fakeServer(path, frames);
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"same",driverId:"driver",onNotification:()=>{}});
	client.start(); await waitFor(() => frames.some((f) => f.type === "session.register"));
	const state = join(dir, "state"); await mkdir(state);
	for (let n = 0; n < 20; n++) await writeFile(join(state, "crew-b.meta"), `${n}\n`);
	await new Promise((resolve) => setTimeout(resolve, 50));
	assert.equal(frames.filter((f) => f.type === "watchtower.register").length, 1);
	client.close(); await closeServer(fake.server, fake.sockets); await rm(dir, {recursive:true,force:true});
});

test("five native daemon restarts manufacture zero completions", async () => {
	const home = await mkdtemp(join(tmpdir(), "rozoro-native-")); const path = join(home, "monitor.sock"); let daemon = await startDaemon(home); let wakes = 0;
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"native-five",driverId:"driver-five",reconnectMs:20,onNotification:()=>{wakes++;}});
	client.start();
	for (let restart = 0; restart < 5; restart++) { await stopDaemon(daemon); daemon = await startDaemon(home); await new Promise((resolve) => setTimeout(resolve, 60)); }
	assert.equal(wakes, 0); client.close(); await stopDaemon(daemon); await rm(home, {recursive:true,force:true});
});

test("five fake socket restarts re-register without manufacturing completions", async () => {
	const dir = await mkdtemp(join(tmpdir(), "rozoro-pi-")); const path = join(dir, "monitor.sock");
	const frames: Record<string, unknown>[] = []; let fake = await fakeServer(path, frames); let wakes = 0;
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"same",driverId:"driver",reconnectMs:20,onNotification:()=>{wakes++;}});
	client.start(); await waitFor(() => frames.some((f) => f.type === "session.register"));
	for (let restart = 1; restart <= 5; restart++) {
		await closeServer(fake.server, fake.sockets); fake = await fakeServer(path, frames);
		await waitFor(() => frames.filter((f) => f.type === "watchtower.register").length >= restart + 1);
	}
	assert.equal(wakes, 0);
	assert.equal(frames.filter((f) => f.type === "turn.stop").length, 0);
	client.close(); await closeServer(fake.server, fake.sockets); await rm(dir, {recursive:true,force:true});
});

test("delivered-unacked restart redelivers exactly one fixed wake in the new epoch", async () => {
	const dir = await mkdtemp(join(tmpdir(), "rozoro-pi-")); const path = join(dir, "monitor.sock");
	const frames: Record<string, unknown>[] = []; let fake = await fakeServer(path, frames); let wakes = 0;
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"same",driverId:"driver",reconnectMs:20,onNotification:()=>{wakes++;}});
	client.start(); await waitFor(() => frames.some((f) => f.type === "session.register"));
	[...fake.sockets][0]!.write('{"v":1,"type":"notification","generation":3,"priority":"normal","task_count":2}\n');
	await waitFor(() => frames.some((f) => f.type === "notification.delivered"));
	await closeServer(fake.server, fake.sockets); fake = await fakeServer(path, frames);
	await waitFor(() => frames.filter((f) => f.type === "watchtower.register").length === 2);
	[...fake.sockets][0]!.write('{"v":1,"type":"notification","generation":3,"priority":"normal","task_count":2}\n');
	await waitFor(() => wakes === 2); await new Promise((resolve) => setTimeout(resolve, 50));
	assert.equal(wakes, 2); assert.equal(frames.filter((f) => f.type === "watchtower.register").length, 2);
	client.close(); await closeServer(fake.server, fake.sockets); await rm(dir, {recursive:true,force:true});
});

test("serializes and deduplicates concurrent clustered notification envelopes", async () => {
	const dir = await mkdtemp(join(tmpdir(), "rozoro-pi-")); const path = join(dir, "monitor.sock");
	const frames: Record<string, unknown>[] = []; const fake = await fakeServer(path, frames); let release!: () => void; let wakes = 0;
	const gate = new Promise<void>((resolve) => { release = resolve; });
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"same",driverId:"driver",onNotification:async()=>{wakes++; await gate;}});
	client.start(); await waitFor(() => frames.some((f) => f.type === "session.register"));
	const socket = [...fake.sockets][0]!; const notice = '{"v":1,"type":"notification","generation":9,"priority":"normal","task_count":4}\n';
	socket.write(notice + notice); await waitFor(() => wakes === 1); release();
	await waitFor(() => frames.some((f) => f.type === "notification.delivered"));
	assert.equal(wakes, 1); assert.equal(frames.filter((f) => f.type === "notification.delivered").length, 1);
	client.close(); await closeServer(fake.server, fake.sockets); await rm(dir, {recursive:true,force:true});
});

test("null malformed partial and oversized frames close safely and reconnect in order", async () => {
	for (const payload of ["null\n", "{}\n", '{"v":1', "x".repeat(MAX_FRAME_BYTES + 1)]) {
		const dir = await mkdtemp(join(tmpdir(), "rozoro-pi-")); const path = join(dir, "monitor.sock");
		const frames: Record<string, unknown>[] = []; const fake = await fakeServer(path, frames);
		const client = new RozoroEventBusClient({socketPath:path,sessionId:"same",driverId:"driver",reconnectMs:20,onNotification:()=>{}});
		client.start(); await waitFor(() => frames.some((f) => f.type === "session.register"));
		[...fake.sockets][0]!.write(payload); if (payload === '{"v":1') [...fake.sockets][0]!.end();
		await waitFor(() => frames.filter((f) => f.type === "watchtower.register").length >= 2);
		client.close(); await closeServer(fake.server, fake.sockets); await rm(dir, {recursive:true,force:true});
	}
});

test("uncertain notification delivery is not confirmed and is redeliverable", async () => {
	const dir = await mkdtemp(join(tmpdir(), "rozoro-pi-")); const path = join(dir, "monitor.sock");
	const frames: Record<string, unknown>[] = []; const fake = await fakeServer(path, frames); let attempts = 0;
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"same",driverId:"driver",onNotification:()=>{attempts++; throw new Error("Pi stopped");}});
	client.start(); await waitFor(() => frames.some((f) => f.type === "session.register"));
	[...fake.sockets][0]!.write('{"v":1,"type":"notification","generation":4,"priority":"normal","task_count":1}\n');
	await waitFor(() => attempts === 1);
	assert.ok(!frames.some((f) => f.type === "notification.delivered"));
	client.close(); await closeServer(fake.server, fake.sockets); await rm(dir, {recursive:true,force:true});
});
