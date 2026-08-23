import { createHash, randomUUID } from "node:crypto";
import { createConnection, type Socket } from "node:net";

export const WAKE_CONTENT = "Rozoro notification pending; run ./bin/rozoro reconcile.";

type Frame = Record<string, unknown> & { v: 1; type: string };
type Pending = { frame: Frame; match: (reply: Frame) => boolean; resolve: () => void };

export type AdapterOptions = {
	socketPath: string;
	sessionId: string;
	driverId: string;
	onNotification: (generation: number) => void | Promise<void>;
	onStatus?: (status: string) => void;
	reconnectMs?: number;
	pollMs?: number;
};

const safeId = (prefix: string, value: string): string => {
	if (/^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$/.test(value)) return value;
	return `${prefix}-${createHash("sha256").update(value).digest("hex").slice(0, 32)}`;
};

export class RozoroEventBusClient {
	private socket?: Socket;
	private buffer = "";
	private stopped = true;
	private reconnectTimer?: ReturnType<typeof setTimeout>;
	private pollTimer?: ReturnType<typeof setInterval>;
	private pending?: Pending;
	private queue: Pending[] = [];
	private producerSeq = Date.now() * 1000;
	private turn = 0;
	private registerQueued = false;
	readonly sessionId: string;
	readonly driverId: string;
	private readonly options: AdapterOptions;

	constructor(options: AdapterOptions) {
		this.options = options;
		this.sessionId = safeId("pi-session", options.sessionId);
		this.driverId = safeId("pi-driver", options.driverId);
	}

	start(): void {
		if (!this.stopped) return;
		this.stopped = false;
		this.connect();
	}

	private connect(): void {
		if (this.stopped || this.socket) return;
		this.options.onStatus?.("event bus: connecting");
		const socket = createConnection(this.options.socketPath);
		this.socket = socket;
		socket.setEncoding("utf8");
		socket.on("connect", () => {
			this.options.onStatus?.("event bus: connected");
			this.register();
			this.publish("session.register");
			this.pollTimer = setInterval(() => this.register(), this.options.pollMs ?? 500);
			this.pollTimer.unref();
		});
		socket.on("data", (chunk: string) => this.consume(chunk));
		socket.on("error", () => undefined);
		socket.on("close", () => this.disconnected(socket));
	}

	private disconnected(socket: Socket): void {
		if (this.socket !== socket) return;
		this.socket = undefined;
		this.buffer = "";
		if (this.pollTimer) clearInterval(this.pollTimer);
		this.pollTimer = undefined;
		if (this.pending) this.queue.unshift(this.pending);
		this.pending = undefined;
		if (this.stopped) return;
		this.options.onStatus?.("event bus: reconnecting");
		this.reconnectTimer = setTimeout(() => this.connect(), this.options.reconnectMs ?? 250);
		this.reconnectTimer.unref();
	}

	private request(frame: Frame, match: Pending["match"]): Promise<void> {
		return new Promise((resolve) => {
			this.queue.push({ frame, match, resolve });
			this.flush();
		});
	}

	private flush(): void {
		if (this.pending || !this.socket?.writable || this.queue.length === 0) return;
		this.pending = this.queue.shift();
		this.socket.write(`${JSON.stringify(this.pending!.frame)}\n`);
	}

	private register(): void {
		if (this.registerQueued) return;
		this.registerQueued = true;
		const requestId = `pi-register-${randomUUID()}`;
		void this.request({ v: 1, type: "watchtower.register", request_id: requestId,
			session_id: this.sessionId, harness: "pi", driver_id: this.driverId },
			(reply) => reply.type === "ok" && reply.request_id === requestId)
			.then(() => { this.registerQueued = false; });
	}

	publish(type: "session.register" | "turn.start" | "turn.stop" | "session.end"): void {
		const producerSeq = ++this.producerSeq;
		const eventId = `${this.sessionId}-${producerSeq}-${randomUUID()}`;
		const frame: Frame = { v: 1, type, event_id: eventId, producer_seq: producerSeq,
			session_id: this.sessionId, harness: "pi", role: "watchtower", driver_id: this.driverId };
		if (type === "turn.start") frame.turn_id = `${this.sessionId}-turn-${++this.turn}`;
		if (type === "turn.stop") {
			frame.turn_id = `${this.sessionId}-turn-${this.turn}`;
			frame.background_active = "unknown";
		}
		void this.request(frame, (reply) => reply.type === "ack" && reply.event_id === eventId);
	}

	private consume(chunk: string): void {
		this.buffer += chunk;
		for (;;) {
			const newline = this.buffer.indexOf("\n");
			if (newline < 0) return;
			const line = this.buffer.slice(0, newline);
			this.buffer = this.buffer.slice(newline + 1);
			let frame: Frame;
			try { frame = JSON.parse(line) as Frame; } catch { this.socket?.destroy(); return; }
			if (frame.type === "notification" && Number.isSafeInteger(frame.generation) && (frame.generation as number) > 0) {
				void this.deliver(frame.generation as number);
				continue;
			}
			if (this.pending?.match(frame)) {
				const done = this.pending;
				this.pending = undefined;
				done.resolve();
				this.flush();
			} else if (frame.type.endsWith("error")) this.socket?.destroy();
		}
	}

	private async deliver(generation: number): Promise<void> {
		try {
			await this.options.onNotification(generation);
		} catch {
			this.socket?.destroy();
			return;
		}
		const requestId = `pi-delivered-${randomUUID()}`;
		void this.request({ v: 1, type: "notification.delivered", request_id: requestId,
			driver_id: this.driverId, generation },
			(reply) => reply.type === "ok" && reply.request_id === requestId);
	}

	close(): void {
		if (this.stopped) return;
		this.stopped = true;
		if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
		if (this.pollTimer) clearInterval(this.pollTimer);
		this.reconnectTimer = undefined;
		this.pollTimer = undefined;
		this.socket?.destroy();
		this.socket = undefined;
		this.options.onStatus?.("event bus: stopped");
	}
}
