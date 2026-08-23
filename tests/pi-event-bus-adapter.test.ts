import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer, type Server, type Socket } from "node:net";
import test from "node:test";
import { RozoroEventBusClient, WAKE_CONTENT } from "../.pi/extensions/rozoro-event-bus-client.ts";

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
	return { server, sockets };
}

const closeServer = async (server: Server, sockets: Set<Socket>) => {
	for (const socket of sockets) socket.destroy();
	await new Promise<void>((resolve) => server.close(() => resolve()));
};

test("uses prose-free registration, publishes only certified Pi lifecycle, and confirms after fixed wake", async () => {
	const dir = await mkdtemp(join(tmpdir(), "rozoro-pi-")); const path = join(dir, "monitor.sock");
	const frames: Record<string, unknown>[] = []; const fake = await fakeServer(path, frames); const delivered: string[] = [];
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"pi-session",driverId:"driver-1",pollMs:10_000,
		onNotification: async () => { delivered.push(WAKE_CONTENT); }});
	client.start(); await waitFor(() => frames.some((f) => f.type === "session.register"));
	client.publish("turn.start"); client.publish("turn.stop");
	await waitFor(() => frames.some((f) => f.type === "turn.stop"));
	const socket = [...fake.sockets][0]!;
	socket.write('{"v":1,"type":"notification","generation":7,"priority":"normal","task_count":3}\n');
	await waitFor(() => frames.some((f) => f.type === "notification.delivered"));
	assert.deepEqual(delivered, ["Rozoro notification pending; run ./bin/rozoro reconcile."]);
	assert.equal(frames.find((f) => f.type === "notification.delivered")!.generation, 7);
	assert.equal(frames.find((f) => f.type === "turn.stop")!.background_active, "unknown");
	assert.ok(!frames.some((f) => "content" in f || "message" in f || "reason" in f));
	client.close(); client.close(); await closeServer(fake.server, fake.sockets); await rm(dir, {recursive:true,force:true});
});

test("five daemon restarts re-register without manufacturing completions", async () => {
	const dir = await mkdtemp(join(tmpdir(), "rozoro-pi-")); const path = join(dir, "monitor.sock");
	const frames: Record<string, unknown>[] = []; let fake = await fakeServer(path, frames); let wakes = 0;
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"same",driverId:"driver",reconnectMs:20,pollMs:10_000,onNotification:()=>{wakes++;}});
	client.start(); await waitFor(() => frames.some((f) => f.type === "session.register"));
	for (let restart = 1; restart <= 5; restart++) {
		await closeServer(fake.server, fake.sockets); fake = await fakeServer(path, frames);
		await waitFor(() => frames.filter((f) => f.type === "watchtower.register").length >= restart + 1);
	}
	assert.equal(wakes, 0);
	assert.equal(frames.filter((f) => f.type === "turn.stop").length, 0);
	client.close(); await closeServer(fake.server, fake.sockets); await rm(dir, {recursive:true,force:true});
});

test("uncertain notification delivery is not confirmed and is redeliverable", async () => {
	const dir = await mkdtemp(join(tmpdir(), "rozoro-pi-")); const path = join(dir, "monitor.sock");
	const frames: Record<string, unknown>[] = []; const fake = await fakeServer(path, frames); let attempts = 0;
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"same",driverId:"driver",pollMs:10_000,onNotification:()=>{attempts++; throw new Error("Pi stopped");}});
	client.start(); await waitFor(() => frames.some((f) => f.type === "session.register"));
	[...fake.sockets][0]!.write('{"v":1,"type":"notification","generation":4,"priority":"normal","task_count":1}\n');
	await waitFor(() => attempts === 1);
	assert.ok(!frames.some((f) => f.type === "notification.delivered"));
	client.close(); await closeServer(fake.server, fake.sockets); await rm(dir, {recursive:true,force:true});
});
