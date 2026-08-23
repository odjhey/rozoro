import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { herdrDriverId, RozoroEventBusClient, WAKE_CONTENT } from "../lib/rozoro-event-bus-client.ts";

const WATCHTOWER_MARKER = "rozoro **watchtower**";
const STATUS_KEY = "rozoro-monitor";

export default function (pi: ExtensionAPI) {
	const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
	const rozoroHome = process.env.ROZORO_HOME || process.env.RZR_HOME || join(homedir(), ".rozoro");

	let currentCtx: ExtensionContext | undefined;
	let busClient: RozoroEventBusClient | undefined;

	const cleanupOnProcessExit = () => busClient?.close();
	process.once("exit", cleanupOnProcessExit);

	pi.on("session_start", async (_event, ctx) => {
		currentCtx = ctx;
		const requested = process.env.ROZORO_WATCHTOWER === "1" || ctx.getSystemPrompt().includes(WATCHTOWER_MARKER);
		if (!requested) return;
		{
			const sessionId = ctx.sessionManager.getSessionId();
			const paneId = process.env.HERDR_PANE_ID;
			if (!paneId) throw new Error("Rozoro event-bus Pi watchtower requires HERDR_PANE_ID");
			const expectedDriverId = herdrDriverId(paneId);
			const registration = await pi.exec(join(repoRoot, "bin", "rozoro"), ["register", "--harness", "pi", "--backend", "herdr"]);
			if (registration.code !== 0) throw new Error(`Rozoro watchtower target registration failed: ${registration.stderr.trim()}`);
			const driverId = registration.stdout.trim();
			if (driverId !== expectedDriverId) throw new Error("Rozoro watchtower target identity does not match the resident Pi pane");
			busClient = new RozoroEventBusClient({
				socketPath: join(rozoroHome, "monitor.sock"), sessionId, driverId,
				onStatus: (status) => ctx.ui.setStatus(STATUS_KEY, status),
				onNotification: () => pi.sendMessage(
					{ customType: "rozoro-event", content: WAKE_CONTENT, display: true },
					{ triggerTurn: true, deliverAs: "followUp" },
				),
			});
			busClient.start();
			return;
		}
	});

	pi.on("agent_start", () => busClient?.publish("turn.start"));
	pi.on("agent_settled", () => busClient?.publish("turn.stop"));

	pi.on("session_shutdown", async () => {
		busClient?.close();
		busClient = undefined;
		process.removeListener("exit", cleanupOnProcessExit);
		currentCtx = undefined;
	});

	pi.registerCommand("rozoro-monitor", {
		description: "Show resident Rozoro event-bus adapter health",
		handler: async (_args, ctx) => {
			currentCtx = ctx;
			ctx.ui.notify(busClient ? "Rozoro event-bus adapter is connected or reconnecting" : "Rozoro event-bus adapter is not active", "info");
		},
	});
}
