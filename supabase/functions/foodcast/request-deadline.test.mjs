import assert from "node:assert/strict";
import test from "node:test";
import { RequestDeadlineError, withRequestDeadline } from "./request-deadline.ts";

test("returns the upstream value before its deadline", async () => {
  assert.equal(await withRequestDeadline(Promise.resolve("ok"), 100), "ok");
});

test("rejects when the upstream operation exceeds its deadline", async () => {
  await assert.rejects(
    withRequestDeadline(new Promise(() => {}), 1),
    error => error instanceof RequestDeadlineError && error.deadlineMs === 1,
  );
});

test("preserves upstream failures", async () => {
  const failure = new Error("upstream failed");
  await assert.rejects(withRequestDeadline(Promise.reject(failure), 100), failure);
});

test("rejects invalid deadlines", async () => {
  await assert.rejects(withRequestDeadline(Promise.resolve("ok"), 0), RangeError);
});
