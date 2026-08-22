import { spawn, type ChildProcess } from "node:child_process";
import { watch, type FSWatcher } from "node:fs";
import { mkdir, readdir } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createInterface, type Interface } from "node:readline";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const ACTIONABLE = new Set(["idle", "done", "blocked", "gone"]);
const WATCHTOWER_MARKER = "rozoro **watchtower**";
const STATUS_KEY = "rozoro-monitor";

export default function (pi: ExtensionAPI) {
	const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
	const watchCommand = join(repoRoot, "bin", "rzr-watch.sh");
	const rozoroHome = process.env.ROZORO_HOME || process.env.RZR_HOME || join(homedir(), ".rozoro");
	const stateDir = join(rozoroHome, "state");

	let currentCtx: ExtensionContext | undefined;
	let child: ChildProcess | undefined;
	let childLines: Interface | undefined;
	let stateWatcher: FSWatcher | undefined;
	let restartTimer: ReturnType<typeof setTimeout> | undefined;
	let retryTimer: ReturnType<typeof setTimeout> | undefined;
	let enabled = false;
	let shuttingDown = false;
	let knownTasks = new Set<string>();
	const retiredChildren = new WeakSet<ChildProcess>();
	const freshTasks = new Set<string>();
	const seen = new Map<string, string>();

	const setStatus = (text?: string) => currentCtx?.ui.setStatus(STATUS_KEY, text);

	async function taskIds(): Promise<Set<string>> {
		try {
			return new Set(
				(await readdir(stateDir))
					.filter((name) => name.endsWith(".meta"))
					.map((name) => name.slice(0, -".meta".length)),
			);
		} catch {
			return new Set();
		}
	}

	function stopChild(): void {
		childLines?.close();
		childLines = undefined;
		if (child) {
			retiredChildren.add(child);
			child.kill("SIGTERM");
		}
		child = undefined;
	}

	function notify(id: string, status: string, previous: string | undefined, initial: boolean): void {
		const newlyTracked = freshTasks.delete(id);
		seen.set(id, status);
		setStatus(`crew ${id}: ${status}`);

		// Startup reconciliation establishes a baseline without waking the model for
		// every task left over from an earlier watchtower session.
		if (previous === undefined && !newlyTracked) return;
		if (previous === status) return;

		currentCtx?.ui.notify(
			`Crew ${id}: ${previous ?? "new"} → ${status}`,
			status === "unknown" || status === "gone" ? "warning" : "info",
		);
		if (!ACTIONABLE.has(status)) return;

		pi.sendMessage(
			{
				customType: "rozoro-event",
				content:
					`[rozoro event] Crew '${id}' changed from ${previous ?? (initial ? "new" : "unknown")} to ${status}. ` +
					`Run './bin/rozoro status ${id}' now, inspect the handoff verdict, and continue the watchtower loop.`,
				display: true,
				details: { id, status, previous, initial },
			},
			// The monitor itself never occupies a tool call. If the watchtower is busy
			// for another reason, serialize this real edge after that turn instead.
			{ triggerTurn: true, deliverAs: "followUp" },
		);
	}

	function consumeLine(line: string): void {
		const [time, id, status, marker] = line.split("\t");
		if (!time || !id || !status) return;
		if (!["idle", "working", "done", "blocked", "unknown", "gone", "shell"].includes(status)) return;
		notify(id, status, seen.get(id), marker === "(initial)");
	}

	async function startChild(): Promise<void> {
		if (!enabled || shuttingDown) return;
		const tasks = await taskIds();
		if (tasks.size === 0) {
			setStatus("crew monitor: waiting");
			return;
		}

		stopChild();
		let stderr = "";
		const next = spawn(watchCommand, [], {
			cwd: repoRoot,
			env: process.env,
			stdio: ["ignore", "pipe", "pipe"],
		});
		child = next;
		if (!next.stdout || !next.stderr) throw new Error("Rozoro monitor pipes were not created");
		childLines = createInterface({ input: next.stdout });
		childLines.on("line", consumeLine);
		next.stderr.on("data", (chunk) => {
			stderr += String(chunk);
		});
		next.on("error", (error) => {
			currentCtx?.ui.notify(`Rozoro monitor failed: ${error.message}`, "error");
		});
		next.on("close", () => {
			if (child === next) {
				child = undefined;
				childLines = undefined;
			}
			if (!enabled || shuttingDown || retiredChildren.has(next)) return;
			if (stderr.includes("no live tasks to watch")) {
				setStatus("crew monitor: waiting");
				return;
			}
			retryTimer = setTimeout(() => void startChild(), 2000);
			retryTimer.unref();
		});
		setStatus(`crew monitor: ${tasks.size} tracked`);
	}

	function scheduleRestart(): void {
		if (!enabled || shuttingDown) return;
		if (restartTimer) clearTimeout(restartTimer);
		restartTimer = setTimeout(() => void startChild(), 150);
		restartTimer.unref();
	}

	async function reconcileTasks(): Promise<void> {
		const next = await taskIds();
		for (const id of next) {
			if (!knownTasks.has(id)) freshTasks.add(id);
		}
		for (const id of knownTasks) {
			if (!next.has(id)) {
				seen.delete(id);
				freshTasks.delete(id);
			}
		}
		knownTasks = next;
		scheduleRestart();
	}

	async function startMonitor(): Promise<void> {
		if (enabled) return;
		enabled = true;
		shuttingDown = false;
		await mkdir(stateDir, { recursive: true });
		knownTasks = await taskIds();
		stateWatcher = watch(stateDir, (_event, filename) => {
			if (filename?.endsWith(".meta")) void reconcileTasks();
		});
		await startChild();
		currentCtx?.ui.notify("Rozoro crew monitor started in the background", "info");
	}

	function stopMonitor(): void {
		enabled = false;
		stateWatcher?.close();
		stateWatcher = undefined;
		if (restartTimer) clearTimeout(restartTimer);
		if (retryTimer) clearTimeout(retryTimer);
		restartTimer = undefined;
		retryTimer = undefined;
		stopChild();
		setStatus(undefined);
	}

	const cleanupOnProcessExit = () => stopMonitor();
	process.once("exit", cleanupOnProcessExit);

	pi.on("session_start", async (_event, ctx) => {
		currentCtx = ctx;
		const requested = process.env.ROZORO_WATCHTOWER === "1" || ctx.getSystemPrompt().includes(WATCHTOWER_MARKER);
		if (requested) await startMonitor();
	});

	pi.on("session_shutdown", async () => {
		shuttingDown = true;
		stopMonitor();
		process.removeListener("exit", cleanupOnProcessExit);
		currentCtx = undefined;
	});

	pi.registerCommand("rozoro-monitor", {
		description: "Control the non-blocking Rozoro crew event monitor (on|off|status)",
		handler: async (args, ctx) => {
			currentCtx = ctx;
			switch (args.trim()) {
				case "":
				case "status":
					ctx.ui.notify(`Rozoro monitor is ${enabled ? "on" : "off"}`, "info");
					break;
				case "on":
					await startMonitor();
					break;
				case "off":
					stopMonitor();
					ctx.ui.notify("Rozoro crew monitor stopped", "info");
					break;
				default:
					ctx.ui.notify("Usage: /rozoro-monitor [on|off|status]", "warning");
			}
		},
	});
}
