import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { chmod, lstat, mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn, type ChildProcess } from "node:child_process";
import { pathToFileURL } from "node:url";
import { createServer, createConnection, type Server, type Socket } from "node:net";
import test from "node:test";
import { herdrDriverId, MAX_FRAME_BYTES, RozoroEventBusClient, WAKE_CONTENT } from "../.pi/lib/rozoro-event-bus-client.ts";

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
				if (frame.type === "watchtower.register" || frame.type === "notification.pending") socket.write(`${JSON.stringify({v:1,type:"ok",request_id:frame.request_id})}\n`);
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
const registerProductionTarget = async (home: string, pane: string): Promise<string> => {
	const fakeRoot = join(home, "fake-herdr"); await mkdir(fakeRoot, {recursive:true});
	await writeFile(join(fakeRoot, `status.${pane}`), "idle\n"); await writeFile(join(fakeRoot, `kind.${pane}`), "pi\n"); await writeFile(join(fakeRoot, `ready.${pane}`), "true\n");
	const child = spawn(join(process.cwd(), "bin/rozoro"), ["register", "--harness", "pi", "--backend", "herdr"],
		{env:{...process.env,PATH:`${join(process.cwd(), "tests/fakes")}:${process.env.PATH}`,ROZORO_HOME:home,HERDR_PANE_ID:pane,FAKE_HERDR_ROOT:fakeRoot,FAKE_HERDR_SOCKET:"fake"}});
	let stdout = ""; child.stdout?.on("data", (chunk) => { stdout += chunk; });
	const code = await new Promise<number|null>((resolve) => child.once("exit", resolve)); assert.equal(code, 0); return stdout.trim();
};

const sendProducer = async (path: string, task = "task-native", session = "crew-native") => {
	const socket = createConnection(path); await new Promise<void>((resolve) => socket.once("connect", resolve));
	const frames = [
		{v:1,type:"session.register",event_id:`crew-register-${randomUUID()}`,producer_seq:1,session_id:session,harness:"claude",role:"crew",task_id:task},
		{v:1,type:"turn.start",event_id:`crew-start-${randomUUID()}`,producer_seq:2,session_id:session,harness:"claude",role:"crew",task_id:task,turn_id:`${session}-turn`},
		{v:1,type:"turn.stop",event_id:`crew-stop-${randomUUID()}`,producer_seq:3,session_id:session,harness:"claude",role:"crew",task_id:task,turn_id:`${session}-turn`,background_active:false},
	];
	for (const frame of frames) {
		socket.write(JSON.stringify(frame) + "\n");
		await new Promise<void>((resolve) => socket.once("data", () => resolve()));
	}
	socket.destroy();
};

const closeServer = async (server: Server, sockets: Set<Socket>) => {
	for (const socket of sockets) socket.destroy();
	await new Promise<void>((resolve) => server.close(() => resolve()));
};

test("native coalescer batches two completions straddling a 500ms adapter poll", async () => {
	const home = await mkdtemp(join(tmpdir(), "rozoro-native-")); const path = join(home, "monitor.sock"); const driver = await registerProductionTarget(home, "cluster:p1");
	const daemon = await startDaemon(home); let wakes = 0;
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"native-cluster",driverId:driver,pollMs:500,onNotification:()=>{wakes++;}});
	client.start(); await new Promise((resolve) => setTimeout(resolve, 450));
	const state = join(home, "state"); await mkdir(state, {recursive:true});
	const rewrite = (async()=>{ for(let i=0;i<12;i++){ await writeFile(join(state,"unrelated.meta"),`pane=unrelated\nnote=${i}\n`); await new Promise(r=>setTimeout(r,8)); } })();
	await sendProducer(path, "task-cluster-a", "crew-cluster-a"); await new Promise((resolve) => setTimeout(resolve, 100));
	await sendProducer(path, "task-cluster-b", "crew-cluster-b"); await rewrite; await waitFor(() => wakes === 1, 5000);
	await new Promise((resolve) => setTimeout(resolve, 600)); assert.equal(wakes, 1);
	const reconcile = spawn(join(process.cwd(), "bin/rozoro"), ["reconcile", "--json"], {env:{...process.env,ROZORO_HOME:home,ROZORO_EVENT_BUS:"1",HERDR_PANE_ID:"cluster:p1"}});
	let stdout = ""; reconcile.stdout?.on("data", (chunk) => { stdout += chunk; }); const code = await new Promise<number|null>((resolve) => reconcile.once("exit", resolve));
	assert.equal(code, 0); assert.deepEqual(JSON.parse(stdout).vanished.sort(), ["task-cluster-a", "task-cluster-b"]);
	client.close(); await stopDaemon(daemon); await rm(home, {recursive:true,force:true});
});

test("native daemon offers a post-registration generation once without epoch churn", async () => {
	const home = await mkdtemp(join(tmpdir(), "rozoro-native-")); const path = join(home, "monitor.sock"); const daemon = await startDaemon(home); let wakes = 0;
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"native-late",driverId:"driver-late",pollMs:30,onNotification:()=>{wakes++;}});
	client.start(); await new Promise((resolve) => setTimeout(resolve, 100)); await sendProducer(path);
	await waitFor(() => wakes === 1, 5000); await new Promise((resolve) => setTimeout(resolve, 150)); assert.equal(wakes, 1);
	client.close(); await stopDaemon(daemon); await rm(home, {recursive:true,force:true});
});

test("native daemon preserves delivered-unacked wake across restart and fixed reconcile identity", async () => {
	const home = await mkdtemp(join(tmpdir(), "rozoro-native-")); const path = join(home, "monitor.sock");
	const driver = herdrDriverId("w7:p12"); assert.equal(await registerProductionTarget(home, "w7:p12"), driver);
	let daemon = await startDaemon(home); await sendProducer(path); const wakes: string[] = [];
	const client = new RozoroEventBusClient({socketPath:path,sessionId:"native-pi-session",driverId:driver,reconnectMs:20,onNotification:()=>{wakes.push(WAKE_CONTENT);}});
	try {
		client.start(); await waitFor(() => wakes.length === 1); await stopDaemon(daemon); daemon = await startDaemon(home);
		await waitFor(() => wakes.length === 2, 5000); await new Promise((resolve) => setTimeout(resolve, 100)); assert.equal(wakes.length, 2);
		const reconcile = spawn(join(process.cwd(), "bin/rozoro"), ["reconcile", "--json"], {env:{...process.env,ROZORO_HOME:home,ROZORO_EVENT_BUS:"1",HERDR_PANE_ID:"w7:p12"}});
		let stdout = "", stderr = ""; reconcile.stdout?.on("data", (chunk) => { stdout += chunk; }); reconcile.stderr?.on("data", (chunk) => { stderr += chunk; });
		const code = await new Promise<number|null>((resolve) => reconcile.once("exit", resolve)); assert.equal(code, 0, stderr); assert.equal(JSON.parse(stdout).driver, driver);
	} finally {
		client.close(); if (daemon.exitCode === null) await stopDaemon(daemon); await rm(home, {recursive:true,force:true});
	}
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
	assert.equal(frames.find((f) => f.type === "turn.stop")!.background_active, false);
	assert.deepEqual(frames.filter((f) => ["session.register","turn.start","turn.stop"].includes(f.type as string))
		.map((f) => f.producer_seq), [1, 2, 3]);
	assert.ok(!frames.some((f) => "content" in f || "message" in f || "reason" in f));
	client.close(); client.close(); await closeServer(fake.server, fake.sockets); await rm(dir, {recursive:true,force:true});
});

test("durable Pi custody is contiguous and reload continues at the exact next sequence", async () => {
	const dir = await mkdtemp(join(tmpdir(), "rozoro-pi-custody-")); const path = join(dir, "monitor.sock");
	const frames: Record<string, unknown>[] = []; const fake = await fakeServer(path, frames);
	let client = new RozoroEventBusClient({socketPath:path,sessionId:"durable",role:"crew",taskId:"task-durable"});
	client.start(); client.publish("turn.start"); client.publish("turn.stop");
	await waitFor(() => frames.filter((frame) => ["session.register","turn.start","turn.stop"].includes(frame.type as string)).length === 3);
	client.close();
	client = new RozoroEventBusClient({socketPath:path,sessionId:"durable",role:"crew",taskId:"task-durable"}); client.start();
	await waitFor(() => frames.filter((frame) => frame.type === "session.register").length === 2);
	assert.deepEqual(frames.filter((frame) => ["session.register","turn.start","turn.stop"].includes(frame.type as string)).map((frame) => frame.producer_seq), [1,2,3,4]);
	client.close(); await closeServer(fake.server, fake.sockets); await rm(dir, {recursive:true,force:true});
});

test("twenty clients sharing one Pi session allocate one contiguous custody stream", async () => {
	const dir = await mkdtemp(join(tmpdir(), "rozoro-pi-shared-")); const path = join(dir, "monitor.sock");
	const moduleUrl=pathToFileURL(join(process.cwd(),".pi/lib/rozoro-event-bus-client.ts")).href;
	const script=`import {RozoroEventBusClient} from ${JSON.stringify(moduleUrl)}; new RozoroEventBusClient({socketPath:${JSON.stringify(path)},sessionId:"shared",role:"crew",taskId:"task-shared"});`;
	await Promise.all(Array.from({length:20},()=>new Promise<void>((resolve,reject)=>{const child=spawn(process.execPath,["--experimental-strip-types","--input-type=module","-e",script]); child.once("exit",code=>code===0?resolve():reject(new Error(`producer exited ${code}`)));})));
	const spool = join(dir,"pi-producers","shared","spool");
	const sequences = (await readdir(spool)).filter((name) => name.endsWith(".json")).map((name) => Number(name.slice(0,16))).sort((a,b)=>a-b);
	assert.deepEqual(sequences, Array.from({length:20}, (_,index)=>index+1));
	await rm(dir,{recursive:true,force:true});
});

test("Pi custody rejects symlinked public and downgraded state", async () => {
	for (const mode of ["symlink","public","downgrade","foreign"] as const) {
		const dir=await mkdtemp(join(tmpdir(),"rozoro-pi-unsafe-")); const producer=join(dir,"pi-producers","unsafe"); await mkdir(producer,{recursive:true,mode:0o700}); await chmod(join(dir,"pi-producers"),0o700); await chmod(producer,0o700);
		if (mode === "symlink") { const foreign=await mkdtemp(join(tmpdir(),"foreign-")); await symlink(foreign,join(producer,"spool")); }
		else if (mode === "foreign") {
			const first=new RozoroEventBusClient({socketPath:join(dir,"monitor.sock"),sessionId:"unsafe",role:"crew",taskId:"task"}); first.close();
			const spool=join(producer,"spool"); const name=(await readdir(spool)).find(item=>item.endsWith(".json"))!; const frame=JSON.parse(await readFile(join(spool,name),"utf8")); frame.task_id="other-task"; await writeFile(join(spool,name),JSON.stringify(frame),{mode:0o600});
		} else { await mkdir(join(producer,"spool")); await chmod(join(producer,"spool"),mode === "public" ? 0o755 : 0o700); await writeFile(join(producer,"custody-version"),mode === "downgrade" ? "1\n" : "2\n",{mode:0o600}); }
		assert.throws(()=>new RozoroEventBusClient({socketPath:join(dir,"monitor.sock"),sessionId:"unsafe",role:"crew",taskId:"task"}),/unsafe|unsupported|foreign/);
		await rm(dir,{recursive:true,force:true});
	}
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
