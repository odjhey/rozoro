import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { herdrDriverId, RozoroEventBusClient, WAKE_CONTENT } from "../lib/rozoro-event-bus-client.ts";

const WATCHTOWER_MARKER = "rozoro **watchtower**";
const STATUS_KEY = "rozoro-monitor";
const positiveDuration = (value: string | undefined, fallback: number) => {
	const parsed = Number(value);
	return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};
const REGISTRATION_RETRY_MS = positiveDuration(process.env.ROZORO_PI_REGISTRATION_RETRY_MS, 500);
const REGISTRATION_TIMEOUT_MS = positiveDuration(process.env.ROZORO_PI_REGISTRATION_TIMEOUT_MS, 10_000);

const sleep = (ms: number, signal: AbortSignal) => new Promise<void>((resolve, reject) => {
	const aborted = () => {
		clearTimeout(timer);
		reject(signal.reason ?? new Error("cancelled"));
	};
	const timer = setTimeout(() => {
		signal.removeEventListener("abort", aborted);
		resolve();
	}, ms);
	signal.addEventListener("abort", aborted, { once: true });
});

export default function (pi: ExtensionAPI) {
	const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
	const rozoroHome = process.env.ROZORO_HOME || process.env.RZR_HOME || join(homedir(), ".rozoro");

	let busClient: RozoroEventBusClient | undefined;
	let startup: AbortController | undefined;

	const cleanupOnProcessExit = () => {
		startup?.abort();
		busClient?.close();
	};
	process.once("exit", cleanupOnProcessExit);

	const initialize = async (ctx: ExtensionContext, signal: AbortSignal) => {
		const prompt = ctx.getSystemPrompt();
		const requested = process.env.ROZORO_WATCHTOWER === "1" || prompt.includes(WATCHTOWER_MARKER);
		const taskId = /^rozoro-task:\s*([^\s]+)$/m.exec(prompt)?.[1];
		if (!requested && !taskId) return;

		const monitor = await pi.exec(join(repoRoot, "bin", "rozoro"), ["monitor", "start"], { signal });
		if (monitor.code !== 0) throw new Error(`Rozoro monitor failed readiness: ${monitor.stderr.trim()}`);
		const sessionId = ctx.sessionManager.getSessionId();
		if (!requested && taskId) {
			if (signal.aborted) return;
			busClient = new RozoroEventBusClient({
				socketPath: join(rozoroHome, "monitor.sock"), sessionId, role: "crew", taskId,
				onStatus: (status) => ctx.ui.setStatus(STATUS_KEY, status),
			});
			busClient.start();
			return;
		}

		const paneId = process.env.HERDR_PANE_ID;
		if (!paneId) throw new Error("Rozoro event-bus Pi watchtower requires HERDR_PANE_ID");
		const expectedDriverId = herdrDriverId(paneId);
		const deadline = Date.now() + REGISTRATION_TIMEOUT_MS;
		let registration;
		for (;;) {
			registration = await pi.exec(join(repoRoot, "bin", "rozoro"), ["register", "--harness", "pi", "--backend", "herdr"], { signal });
			if (registration.code === 0) break;
			const error = registration.stderr.trim();
			if (!error.includes("not interactive_ready yet") || Date.now() >= deadline) {
				throw new Error(`Rozoro watchtower target registration failed: ${error}`);
			}
			await sleep(Math.min(REGISTRATION_RETRY_MS, Math.max(0, deadline - Date.now())), signal);
		}
		if (signal.aborted) return;
		const driverId = registration.stdout.trim();
		if (driverId !== expectedDriverId) throw new Error("Rozoro watchtower target identity does not match the resident Pi pane");
		busClient = new RozoroEventBusClient({
			socketPath: join(rozoroHome, "monitor.sock"), sessionId, driverId,
			onStatus: (status) => ctx.ui.setStatus(STATUS_KEY, status),
			onRegistered: async () => {
				if (signal.aborted) return;
				const activated = await pi.exec(join(repoRoot, "bin", "rzr-event-bus-client.py"), ["authority-activate", "--driver", driverId], { signal });
				if (activated.code !== 0) throw new Error(`Rozoro authority activation failed: ${activated.stderr.trim()}`);
			},
			onNotification: () => pi.sendMessage(
				{ customType: "rozoro-event", content: WAKE_CONTENT, display: true },
				{ triggerTurn: true, deliverAs: "followUp" },
			),
		});
		busClient.start();
	};

	pi.on("session_start", (_event, ctx) => {
		startup?.abort();
		busClient?.close();
		busClient = undefined;
		const controller = new AbortController();
		startup = controller;
		// Do not await Herdr readiness from session_start: Herdr cannot mark Pi
		// interactive_ready until this lifecycle handler returns.
		void initialize(ctx, controller.signal).catch((error) => {
			if (!controller.signal.aborted) {
				ctx.ui.setStatus(STATUS_KEY, "inactive");
				ctx.ui.notify(error instanceof Error ? error.message : String(error), "error");
			}
		});
	});

	pi.on("agent_start", () => busClient?.publish("turn.start"));
	pi.on("agent_settled", () => busClient?.publish("turn.stop"));

	pi.on("session_shutdown", async () => {
		startup?.abort();
		startup = undefined;
		busClient?.close();
		busClient = undefined;
		process.removeListener("exit", cleanupOnProcessExit);
	});

	pi.registerCommand("rozoro-monitor", {
		description: "Show resident Rozoro event-bus adapter health",
		handler: async (_args, ctx) => {
			ctx.ui.notify(busClient ? "Rozoro event-bus adapter is connected or reconnecting" : "Rozoro event-bus adapter is not active", "info");
		},
	});
}
