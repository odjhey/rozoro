import { randomUUID } from "node:crypto";
import { closeSync, constants, fstatSync, fsyncSync, ftruncateSync, lstatSync, mkdirSync, openSync, readSync, writeSync } from "node:fs";
import { lstat, realpath } from "node:fs/promises";
import { createConnection, type Socket } from "node:net";
import { dirname, join } from "node:path";

export const WAKE_CONTENT = "Rozoro notification pending; run ./bin/rozoro reconcile.";
export const MAX_FRAME_BYTES = 1_048_576;
export const MAX_PRODUCER_SEQ = 9_007_199_254_740_991;

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

const NOFOLLOW = constants.O_NOFOLLOW ?? 0;
const DIGITS = /^[0-9]+$/;
const privatelyOwned = (info: { uid: number; mode: number }) => {
	const uid = process.geteuid?.();
	return (uid === undefined || info.uid === uid) && (info.mode & 0o077) === 0;
};

const readCounter = (fd: number): number => {
	const buffer = Buffer.alloc(64);
	const text = buffer.subarray(0, readSync(fd, buffer, 0, buffer.length, 0)).toString("ascii").trim();
	if (!text) return 0;
	const value = Number(text);
	if (!DIGITS.test(text) || !Number.isSafeInteger(value)) throw new Error("invalid Rozoro producer sequence state");
	return value;
};

const writeCounter = (fd: number, value: number): void => {
	const data = Buffer.from(String(value), "ascii");
	let written = 0;
	while (written < data.length) written += writeSync(fd, data, written, data.length - written, written);
	ftruncateSync(fd, data.length);
	fsyncSync(fd);
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
	private producerSeq: number;
	private turn = 0;
	private delivering?: number;
	private notifications: number[] = [];
	private epoch = 0;
	private deliveredThisEpoch = new Set<number>();
	private readonly sessionRegistration: Pending;
	private readonly producerSeqDir: string;
	private readonly producerSeqPath: string;
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
		this.producerSeqDir = join(dirname(options.socketPath), "producer-seq");
		this.producerSeqPath = join(this.producerSeqDir, `${this.sessionId}.seq`);
		this.producerSeq = this.counter(readCounter);
		this.sessionRegistration = { frame: this.event("session.register"), kind: "event" };
	}

	private counter<T>(run: (fd: number) => T): T {
		try { mkdirSync(this.producerSeqDir, 0o700); }
		catch (error) { if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error; }
		const directory = lstatSync(this.producerSeqDir);
		if (!directory.isDirectory() || !privatelyOwned(directory)) throw new Error("unsafe Rozoro producer sequence directory");
		const fd = openSync(this.producerSeqPath, constants.O_RDWR | constants.O_CREAT | NOFOLLOW, 0o600);
		try {
			const info = fstatSync(fd);
			if (!info.isFile() || !privatelyOwned(info)) throw new Error("unsafe Rozoro producer sequence file");
			return run(fd);
		} finally { closeSync(fd); }
	}

	private commit(seq: number): void {
		try { this.counter((fd) => { if (readCounter(fd) < seq) writeCounter(fd, seq); }); }
		catch { this.options.onStatus?.("event bus: producer sequence not durable"); }
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
				this.queue.unshift(this.sessionRegistration); this.flush();
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
		const seq = this.producerSeq + 1;
		if (seq > MAX_PRODUCER_SEQ) throw new Error(`Rozoro producer sequence exhausted for ${this.sessionId}`);
		this.producerSeq = seq;
		const frame: Frame = { v: 1, type, event_id: `${this.sessionId}-${seq}-${randomUUID()}`, producer_seq: seq,
			session_id: this.sessionId, harness: "pi", role: this.role };
		if (this.role === "watchtower") frame.driver_id = this.driverId; else frame.task_id = this.taskId;
		if (type === "turn.start") frame.turn_id = `${this.sessionId}-turn-${++this.turn}`;
		if (type === "turn.stop") { frame.turn_id = `${this.sessionId}-turn-${this.turn}`; frame.background_active = false; }
		return frame;
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
			this.commit(this.pending.frame.producer_seq as number);
		} else if (!exact(frame, ["v", "type", "request_id"]) || frame.v !== 1 || frame.type !== "ok" ||
			frame.request_id !== this.pending.frame.request_id) return false;
		this.pending = undefined; this.flush(); return true;
	}

	private async finishRegistration(epoch: number): Promise<void> {
		try {
			await this.options.onRegistered?.();
			if (!this.registered || this.epoch !== epoch || this.stopped) return;
			this.options.onStatus?.("event bus: connected / authority active");
			if (!this.queue.some((item) => item.frame.event_id === this.sessionRegistration.frame.event_id)) this.queue.unshift(this.sessionRegistration);
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
