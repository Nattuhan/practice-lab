import assert from "node:assert/strict";
import test from "node:test";
import { jobElapsedSeconds, queueItemClass } from "../src/job-status.js";

test("waiting does not count time; processing starts when the worker takes the job", () => {
  const job = { stage: "queued", started_at: 100, execution_started_at: null };
  assert.equal(jobElapsedSeconds(job, 700), 0);
  assert.equal(jobElapsedSeconds(job, 900), 0);
  Object.assign(job, { stage: "running", execution_started_at: 900 });
  assert.equal(jobElapsedSeconds(job, 900), 0);
  assert.equal(jobElapsedSeconds(job, 912.9), 12);
  job.stage = "stems";
  assert.equal(jobElapsedSeconds(job, 925), 25);
});

test("completed and canceled durations stay fixed during later polls", () => {
  for (const stage of ["done", "error", "canceled"]) {
    const job = { stage, done: true, execution_started_at: 900, finished_at: 912.9 };
    assert.equal(jobElapsedSeconds(job, 1000), 12);
    assert.equal(jobElapsedSeconds(job, 2000), 12);
  }
  assert.equal(jobElapsedSeconds({ stage: "canceled", done: true, execution_started_at: null, started_at: 100, finished_at: 900 }, 1000), 0);
  assert.equal(jobElapsedSeconds({ stage: "done", done: true, started_at: 100, updated_at: 112 }, 900), 12);
});

test("waiting, running, interrupted and terminal states have distinct colors", () => {
  assert.equal(queueItemClass({ stage: "queued" }), "queued");
  assert.equal(queueItemClass({ stage: "stems" }), "running");
  assert.equal(queueItemClass({ stage: "interrupted", done: true, interrupted: true }), "interrupted");
  assert.equal(queueItemClass({ stage: "done", done: true }), "done");
  assert.equal(queueItemClass({ stage: "canceled", done: true }), "canceled");
  assert.equal(queueItemClass({ stage: "error", done: true, error: "Failed" }), "error");
});
