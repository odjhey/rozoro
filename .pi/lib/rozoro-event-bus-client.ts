import { randomUUID } from "node:crypto";
import { closeSync, existsSync, fsyncSync, lstatSync, mkdirSync, openSync, readFileSync, readdirSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { lstat, realpath } from "node:fs/promises";
import { createConnection, type Socket } from "node:net";
import { dirname, join, resolve } from "node:path";

export const WAKE_CONTENT = "Rozoro notification pending; run ./bin/rozoro reconcile.";
export const MAX_FRAME_BYTES = 1_048_576;

export type AdapterOptions = {
	socketPath: string;
	sessionId: string;
	driverId?: string;
	taskId?: string;
	role?: "watchtower" | "crew";
	onNotification?: (generation: number) => void | Promise<void>;
	onStatus?: (status: string) => void;
	onRegistered?: () => void | Promise<void>;
	reconnectMs?: number;
	pollMs?: number;
	/** Owner-private durable producer custody; defaults beside monitor.sock. */
	producerStateDir?: string;
};

type Frame = Record<string, unknown>;
type Pending = { frame: Frame; kind: "event" | "delivery" | "poll" };
type SocketIdentity = { dev: number; ino: number };
const ID = /^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$/;
const own = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);
const exact = (value: Frame, required: string[]) =>
	Object.keys(value).length === required.length && required.every((key) => own(value, key));
const positive = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) > 0;
export const herdrDriverId = (paneId: string): string => {
	const safe = paneId.replace(/[^A-Za-z0-9._-]/g, "_").replace(/^_+|_+$/g, "") || "x";
	return `herdr-${safe}`.slice(0, 120);
};

const safeId = (value: string, label: string) => {
	if (!ID.test(value)) throw new Error(`${label} is not a protocol identifier`);
	return value;
};

export class RozoroEventBusClient {
	private socket?: Socket;
	private chunks: Buffer[] = [];
	private bufferedBytes = 0;
	private stopped = true;
	private reconnectTimer?: ReturnType<typeof setTimeout>;
	private pollTimer?: ReturnType<typeof setInterval>;
	private connecting = false;
	private registered = false;
	private registrationRequest = "";
	private pending?: Pending;
	private queue: Pending[] = [];
	private producerSeq = 0;
	private readonly producerDir: string;
	private readonly spoolDir: string;
	private readonly cursorPath: string;
	private readonly versionPath: string;
	private readonly lockPath: string;
	private turn = 0;
	private delivering?: number;
	private notifications: number[] = [];
	private epoch = 0;
	private deliveredThisEpoch = new Set<number>();
	private readonly sessionRegistration: Pending;
	readonly sessionId: string;
	readonly driverId: string;
	readonly taskId: string;
	readonly role: "watchtower" | "crew";
	private readonly options: AdapterOptions;

	constructor(options: AdapterOptions) {
		this.options = options;
		this.sessionId = safeId(options.sessionId, "Pi session id");
		this.role = options.role ?? "watchtower";
		this.driverId = options.driverId ? safeId(options.driverId, "Pi driver id") : "";
		this.taskId = options.taskId ? safeId(options.taskId, "Pi task id") : "";
		if (this.role === "watchtower" && !this.driverId) throw new Error("Pi watchtower requires driver id");
		if (this.role === "crew" && !this.taskId) throw new Error("Pi crew requires task id");
		this.producerDir = options.producerStateDir ?? join(dirname(options.socketPath), "pi-producers", this.sessionId);
		this.spoolDir = join(this.producerDir, "spool");
		this.cursorPath = join(this.producerDir, "cursor-v1");
		this.versionPath = join(this.producerDir, "custody-version");
		this.lockPath = join(this.producerDir, ".allocation-lock");
		this.restoreProducer();
		this.sessionRegistration = { frame: this.event("session.register"), kind: "event" };
		this.queue.push(this.sessionRegistration);
	}

	start(): void {
		if (!this.stopped) return;
		this.stopped = false;
		void this.connect();
	}

	private async socketIdentity(): Promise<SocketIdentity> {
		const home = dirname(this.options.socketPath);
		const [canonical, homeInfo, socketInfo] = await Promise.all([realpath(home), lstat(home), lstat(this.options.socketPath)]);
		const uid = process.geteuid?.();
		if (!canonical || !homeInfo.isDirectory() || (uid !== undefined && homeInfo.uid !== uid) || (homeInfo.mode & 0o077) !== 0)
			throw new Error("unsafe Rozoro home");
		if (!socketInfo.isSocket() || (uid !== undefined && socketInfo.uid !== uid) || (socketInfo.mode & 0o077) !== 0)
			throw new Error("unsafe monitor socket");
		return { dev: socketInfo.dev, ino: socketInfo.ino };
	}

	private async connect(): Promise<void> {
		if (this.stopped || this.socket || this.connecting) return;
		this.connecting = true;
		this.options.onStatus?.("event bus: connecting");
		try {
			const before = await this.socketIdentity();
			if (this.stopped) return;
			const socket = createConnection(this.options.socketPath);
			this.socket = socket;
			socket.on("connect", () => void this.connected(socket, before));
			socket.on("data", (chunk: Buffer) => this.consume(socket, chunk));
			socket.on("error", () => undefined);
			socket.on("close", () => this.disconnected(socket));
		} catch {
			this.scheduleReconnect();
		} finally {
			this.connecting = false;
		}
	}

	private async connected(socket: Socket, before: SocketIdentity): Promise<void> {
		try {
			const after = await this.socketIdentity();
			if (this.socket !== socket || before.dev !== after.dev || before.ino !== after.ino) throw new Error("socket identity changed");
			if (this.role === "crew") {
				this.registered = true; this.epoch++;
				this.options.onStatus?.("event bus: connected / crew producer");
				if (!this.queue.some((item) => item.frame.event_id === this.sessionRegistration.frame.event_id)) this.queue.push(this.sessionRegistration);
				this.flush();
			} else {
				this.registrationRequest = `pi-register-${randomUUID()}`;
				this.write({ v: 1, type: "watchtower.register", request_id: this.registrationRequest,
					session_id: this.sessionId, harness: "pi", driver_id: this.driverId });
			}
		} catch { socket.destroy(); }
	}

	private disconnected(socket: Socket): void {
		if (this.socket !== socket) return;
		this.socket = undefined;
		this.registered = false;
		this.registrationRequest = "";
		this.chunks = [];
		this.bufferedBytes = 0;
		if (this.pollTimer) clearInterval(this.pollTimer);
		this.pollTimer = undefined;
		this.delivering = undefined;
		this.notifications = [];
		this.deliveredThisEpoch.clear();
		if (this.pending?.kind === "event") this.queue.unshift(this.pending);
		this.pending = undefined;
		this.queue = this.queue.filter((item) => item.kind === "event");
		this.scheduleReconnect();
	}

	private scheduleReconnect(): void {
		if (this.stopped || this.reconnectTimer) return;
		this.options.onStatus?.("event bus: reconnecting");
		this.reconnectTimer = setTimeout(() => {
			this.reconnectTimer = undefined;
			void this.connect();
		}, this.options.reconnectMs ?? 250);
		this.reconnectTimer.unref();
	}

	private validateCustodyEntry(path: string, kind: "file" | "directory"): void {
		const info = lstatSync(path); const uid = process.geteuid?.();
		const validKind = kind === "file" ? info.isFile() : info.isDirectory();
		if (!validKind || info.isSymbolicLink() || (uid !== undefined && info.uid !== uid) || (info.mode & 0o077) !== 0)
			throw new Error(`unsafe Pi producer custody ${kind}`);
	}

	private validateRestoredFrame(frame: Frame): void {
		if (!positive(frame.producer_seq) || typeof frame.event_id !== "string" ||
			frame.session_id !== this.sessionId || frame.harness !== "pi" || frame.role !== this.role ||
			(this.role === "crew" ? frame.task_id !== this.taskId || own(frame,"driver_id") :
				frame.driver_id !== this.driverId || own(frame,"task_id")) ||
			!["session.register","turn.start","turn.stop"].includes(frame.type as string))
			throw new Error("foreign Pi producer spool envelope");
	}

	private restoreProducer(): void {
		const home = resolve(dirname(this.options.socketPath));
		const state = resolve(this.producerDir);
		if (state !== home && !state.startsWith(`${home}/`)) throw new Error("Pi producer custody must stay inside Rozoro home");
		this.validateCustodyEntry(home, "directory");
		for (const directory of [dirname(this.producerDir), this.producerDir, this.spoolDir]) {
			try { mkdirSync(directory, {mode: 0o700}); }
			catch (error) { if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error; }
			this.validateCustodyEntry(directory, "directory");
		}
		if (existsSync(this.versionPath)) {
			this.validateCustodyEntry(this.versionPath, "file");
			if (readFileSync(this.versionPath, "utf8") !== "2\n") throw new Error("unsupported Pi producer custody version");
		} else {
			if (existsSync(this.cursorPath) || readdirSync(this.spoolDir).length) throw new Error("unversioned Pi producer custody requires explicit rollback/reset");
			try { writeFileSync(this.versionPath, "2\n", {mode: 0o600, flag: "wx"}); }
			catch (error) { if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error; }
			this.validateCustodyEntry(this.versionPath, "file");
			if (readFileSync(this.versionPath, "utf8") !== "2\n") throw new Error("unsupported Pi producer custody version");
		}
		if (existsSync(this.cursorPath)) {
			this.validateCustodyEntry(this.cursorPath, "file");
			const raw = readFileSync(this.cursorPath, "utf8").trim();
			if (!/^(0|[1-9][0-9]*)$/.test(raw) || !Number.isSafeInteger(Number(raw))) throw new Error("invalid Pi producer cursor");
			this.producerSeq = Number(raw);
		}
		const backlog = readdirSync(this.spoolDir).filter((name) => name.endsWith(".json")).map((name) => {
			try {
				const path = join(this.spoolDir, name); this.validateCustodyEntry(path, "file");
				const frame = JSON.parse(readFileSync(path, "utf8")) as Frame;
				this.validateRestoredFrame(frame);
				return frame;
			} catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined; throw error; }
		}).filter((frame): frame is Frame => frame !== undefined)
			.sort((a, b) => (a.producer_seq as number) - (b.producer_seq as number));
		for (const frame of backlog) {
			this.producerSeq = Math.max(this.producerSeq, frame.producer_seq as number);
			this.queue.push({frame, kind: "event"});
		}
	}

	private withAllocationLock<T>(operation: () => T): T {
		for (let attempt = 0; ; attempt++) {
			try {
				writeFileSync(this.lockPath, `${process.pid}\n`, {mode: 0o600, flag: "wx"}); break;
			} catch (error) {
				if ((error as NodeJS.ErrnoException).code !== "EEXIST" || attempt > 500) throw error;
				try {
					this.validateCustodyEntry(this.lockPath, "file");
					const owner = Number(readFileSync(this.lockPath, "utf8").trim());
					if (Number.isSafeInteger(owner)) try { process.kill(owner, 0); } catch { unlinkSync(this.lockPath); continue; }
				} catch (lockError) { if ((lockError as NodeJS.ErrnoException).code !== "ENOENT") throw lockError; }
				Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 2);
			}
		}
		try { return operation(); } finally { unlinkSync(this.lockPath); }
	}

	private currentProducerSeq(): number {
		let current = 0;
		if (existsSync(this.cursorPath)) current = Number(readFileSync(this.cursorPath, "utf8").trim());
		for (const name of readdirSync(this.spoolDir).filter((item) => item.endsWith(".json"))) {
			try {
				this.validateCustodyEntry(join(this.spoolDir, name), "file");
				const frame = JSON.parse(readFileSync(join(this.spoolDir, name), "utf8")) as Frame;
				this.validateRestoredFrame(frame);
				current = Math.max(current, frame.producer_seq);
			} catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
		}
		return current;
	}

	private persistEvent(frame: Frame): void {
		const seq = frame.producer_seq as number;
		const target = join(this.spoolDir, `${String(seq).padStart(16, "0")}-${frame.event_id}.json`);
		const temporary = `${target}.${process.pid}.tmp`;
		writeFileSync(temporary, JSON.stringify(frame), {mode: 0o600, flag: "wx"});
		renameSync(temporary, target);
		const spoolFd = openSync(this.spoolDir, "r"); try { fsyncSync(spoolFd); } finally { closeSync(spoolFd); }
		const cursorTmp = `${this.cursorPath}.${process.pid}.tmp`;
		writeFileSync(cursorTmp, `${seq}\n`, {mode: 0o600}); renameSync(cursorTmp, this.cursorPath);
		const producerFd = openSync(this.producerDir, "r"); try { fsyncSync(producerFd); } finally { closeSync(producerFd); }
	}

	private releaseEvent(frame: Frame): void {
		const prefix = `${String(frame.producer_seq as number).padStart(16, "0")}-${frame.event_id}`;
		const name = readdirSync(this.spoolDir).find((item) => item === `${prefix}.json`);
		if (name) { unlinkSync(join(this.spoolDir, name)); const fd = openSync(this.spoolDir, "r"); try { fsyncSync(fd); } finally { closeSync(fd); } }
	}

	private write(frame: Frame): void { this.socket?.write(`${JSON.stringify(frame)}\n`); }

	private poll(): void {
		if (!this.registered || this.pending?.kind === "poll" || this.queue.some((item) => item.kind === "poll")) return;
		this.queue.push({ frame: { v: 1, type: "notification.pending", request_id: `pi-poll-${randomUUID()}`,
			driver_id: this.driverId }, kind: "poll" });
		this.flush();
	}

	private flush(): void {
		if (!this.registered || this.pending || !this.socket?.writable || this.queue.length === 0) return;
		this.pending = this.queue.shift();
		this.write(this.pending!.frame);
	}

	private event(type: "session.register" | "turn.start" | "turn.stop"): Frame {
		return this.withAllocationLock(() => {
		const seq = this.currentProducerSeq() + 1;
		const frame: Frame = { v: 1, type, event_id: `${this.sessionId}-${seq}-${randomUUID()}`, producer_seq: seq,
			session_id: this.sessionId, harness: "pi", role: this.role };
		if (this.role === "watchtower") frame.driver_id = this.driverId; else frame.task_id = this.taskId;
		if (type === "turn.start") frame.turn_id = `${this.sessionId}-turn-${++this.turn}`;
		if (type === "turn.stop") { frame.turn_id = `${this.sessionId}-turn-${this.turn}`; frame.background_active = false; }
		this.persistEvent(frame); this.producerSeq = seq;
		return frame;
		});
	}

	publish(type: "turn.start" | "turn.stop"): void {
		if (this.stopped) return;
		this.queue.push({ frame: this.event(type), kind: "event" });
		this.flush();
	}

	private consume(socket: Socket, chunk: Buffer): void {
		if (this.socket !== socket || this.stopped) return;
		this.chunks.push(chunk); this.bufferedBytes += chunk.length;
		if (this.bufferedBytes > MAX_FRAME_BYTES && !Buffer.concat(this.chunks).includes(0x0a)) { socket.destroy(); return; }
		let data = Buffer.concat(this.chunks);
		for (;;) {
			const newline = data.indexOf(0x0a);
			if (newline < 0) break;
			if (newline + 1 > MAX_FRAME_BYTES) { socket.destroy(); return; }
			const raw = data.subarray(0, newline); data = data.subarray(newline + 1);
			let value: unknown;
			try { value = JSON.parse(raw.toString("utf8")); } catch { socket.destroy(); return; }
			if (!value || typeof value !== "object" || Array.isArray(value) || !this.handle(value as Frame)) { socket.destroy(); return; }
		}
		this.chunks = data.length ? [data] : []; this.bufferedBytes = data.length;
		if (this.bufferedBytes > MAX_FRAME_BYTES) socket.destroy();
	}

	private handle(frame: Frame): boolean {
		if (!this.registered) {
			if (!exact(frame, ["v", "type", "request_id"]) || frame.v !== 1 || frame.type !== "ok" || frame.request_id !== this.registrationRequest) return false;
			this.registered = true;
			this.epoch++;
			void this.finishRegistration(this.epoch);
			return true;
		}
		if (frame.type === "notification") {
			if (!exact(frame, ["v", "type", "generation", "priority", "task_count"]) || frame.v !== 1 ||
				!positive(frame.generation) || !["normal", "urgent"].includes(frame.priority as string) ||
				!Number.isSafeInteger(frame.task_count) || (frame.task_count as number) < 0) return false;
			void this.deliver(frame.generation as number);
			return true;
		}
		if (!this.pending) return false;
		if (this.pending.kind === "event") {
			if (!exact(frame, ["v", "type", "event_id", "durable_seq"]) || frame.v !== 1 || frame.type !== "ack" ||
				frame.event_id !== this.pending.frame.event_id || !positive(frame.durable_seq)) return false;
			this.releaseEvent(this.pending.frame);
		} else if (!exact(frame, ["v", "type", "request_id"]) || frame.v !== 1 || frame.type !== "ok" ||
			frame.request_id !== this.pending.frame.request_id) return false;
		this.pending = undefined; this.flush(); return true;
	}

	private async finishRegistration(epoch: number): Promise<void> {
		try {
			await this.options.onRegistered?.();
			if (!this.registered || this.epoch !== epoch || this.stopped) return;
			this.options.onStatus?.("event bus: connected / authority active");
			if (!this.queue.some((item) => item.frame.event_id === this.sessionRegistration.frame.event_id)) this.queue.push(this.sessionRegistration);
			this.pollTimer = setInterval(() => this.poll(), this.options.pollMs ?? 500);
			this.pollTimer.unref();
			this.flush();
		} catch { this.socket?.destroy(); }
	}

	private async deliver(generation: number): Promise<void> {
		if (this.stopped || this.deliveredThisEpoch.has(generation) || this.delivering === generation || this.notifications.includes(generation)) return;
		if (this.delivering !== undefined) { this.notifications.push(generation); return; }
		const epoch = this.epoch;
		this.delivering = generation;
		try {
			if (!this.options.onNotification) throw new Error("notification delivered to non-watchtower adapter");
			await this.options.onNotification(generation);
			if (this.stopped || !this.registered || this.epoch !== epoch) return;
			this.deliveredThisEpoch.add(generation);
			const requestId = `pi-delivered-${randomUUID()}`;
			this.queue.push({ frame: { v: 1, type: "notification.delivered", request_id: requestId,
				driver_id: this.driverId, generation }, kind: "delivery" });
			this.flush();
		} catch { this.socket?.destroy(); }
		finally {
			this.delivering = undefined;
			const next = this.notifications.shift();
			if (next !== undefined && this.registered && this.epoch === epoch) void this.deliver(next);
		}
	}

	close(): void {
		if (this.stopped) return;
		this.stopped = true;
		if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
		if (this.pollTimer) clearInterval(this.pollTimer);
		this.reconnectTimer = undefined;
		this.pollTimer = undefined;
		const socket = this.socket; this.socket = undefined;
		if (socket) { socket.removeAllListeners(); socket.destroy(); }
		this.queue = []; this.pending = undefined; this.notifications = []; this.delivering = undefined; this.chunks = []; this.bufferedBytes = 0;
		this.options.onStatus?.("event bus: stopped");
	}
}
