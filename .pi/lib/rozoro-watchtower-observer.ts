export interface WatchProjection {
	id?: unknown;
	runtime_status?: unknown;
	turn?: { report_status?: unknown };
	action?: { required?: unknown; edge_id?: unknown; reason?: unknown };
}

export interface ActionableProjection {
	id: string;
	runtimeStatus: string;
	reportStatus: string;
	reason: string;
	edgeId: string;
	content: string;
}

export function isTaskKey(value: unknown): value is string {
	return typeof value === "string"
		&& value.length > 0
		&& value.length <= 120
		&& value !== "."
		&& value !== ".."
		&& /^[A-Za-z0-9._-]+$/.test(value);
}

/**
 * Observe one watcher projection. The first projection for an already tracked
 * task is a baseline; a newly discovered task can opt out so its first edge is
 * not lost to the create/subscribe race. Stable edge IDs are emitted once.
 */
export function observeProjection(
	seenEdges: Map<string, Set<string>>,
	projection: WatchProjection,
	suppressFirst: boolean,
): ActionableProjection | undefined {
	if (!isTaskKey(projection.id) || typeof projection.runtime_status !== "string" || !projection.runtime_status) return;

	const first = !seenEdges.has(projection.id);
	const edges = seenEdges.get(projection.id) ?? new Set<string>();
	seenEdges.set(projection.id, edges);

	if (projection.action?.required !== true) return;
	if (typeof projection.action.edge_id !== "string" || !projection.action.edge_id) return;
	if (edges.has(projection.action.edge_id)) return;
	edges.add(projection.action.edge_id);
	if (first && suppressFirst) return;

	const reason = typeof projection.action.reason === "string" && projection.action.reason
		? projection.action.reason
		: "action required";
	return {
		id: projection.id,
		runtimeStatus: projection.runtime_status,
		reportStatus: typeof projection.turn?.report_status === "string" ? projection.turn.report_status : "unknown",
		reason,
		edgeId: projection.action.edge_id,
		content: `[rozoro event] Crew ${projection.id} has an actionable update. Run ./bin/rozoro status ${projection.id}, handle the reported verdict or inputs, and continue the watchtower loop.`,
	};
}
