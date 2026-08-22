import assert from "node:assert/strict";
import test from "node:test";
import { observeProjection } from "../.pi/extensions/rozoro-watchtower-observer.ts";

const action = (id: string, edgeId: unknown, required: unknown = true) => ({
	id,
	runtime_status: "done",
	turn: { report_status: "done" },
	action: { required, edge_id: edgeId, reason: "new handoff" },
});

test("suppresses an actionable startup baseline and its restart replay", () => {
	const seen = new Map<string, Set<string>>();
	assert.equal(observeProjection(seen, action("crew-1", "edge-a"), true), undefined);
	assert.equal(observeProjection(seen, action("crew-1", "edge-a"), true), undefined);
});

test("emits a fresh edge after a non-actionable baseline exactly once", () => {
	const seen = new Map<string, Set<string>>();
	assert.equal(observeProjection(seen, action("crew-1", "ignored", false), true), undefined);
	assert.ok(observeProjection(seen, action("crew-1", "edge-a"), true));
	assert.equal(observeProjection(seen, action("crew-1", "edge-a"), true), undefined);
});

test("emits each distinct stable edge ID once", () => {
	const seen = new Map<string, Set<string>>();
	observeProjection(seen, action("crew-1", "baseline"), true);
	assert.ok(observeProjection(seen, action("crew-1", "edge-a"), true));
	assert.ok(observeProjection(seen, action("crew-1", "edge-b"), true));
	assert.equal(observeProjection(seen, action("crew-1", "edge-a"), true), undefined);
});

test("emits the first actionable snapshot for a newly tracked task", () => {
	const event = observeProjection(new Map(), action("new-task", "edge-a"), false);
	assert.ok(event);
	assert.match(event.content, /\.\/bin\/rozoro status new-task/);
	assert.doesNotMatch(event.content, /reconcile/);
});

test("rejects malformed task keys and required actions without edge IDs", () => {
	for (const id of ["", ".", "../escape", "has space", "x".repeat(121)]) {
		assert.equal(observeProjection(new Map(), action(id, "edge-a"), false), undefined);
	}
	assert.equal(observeProjection(new Map(), action("crew-1", undefined), false), undefined);
	assert.equal(observeProjection(new Map(), action("crew-1", "", true), false), undefined);
});

test("task state removal permits a later incarnation to be fresh", () => {
	const seen = new Map<string, Set<string>>();
	observeProjection(seen, action("crew-1", "edge-a"), false);
	seen.delete("crew-1");
	assert.ok(observeProjection(seen, action("crew-1", "edge-a"), false));
});
