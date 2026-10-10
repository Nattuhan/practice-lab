// Queue time is not processing time. Keep terminal durations fixed while other
// jobs continue polling, and support statuses saved before execution timestamps.
export const jobElapsedSeconds = (job, now = Date.now() / 1000, fallbackStartedAt = now) => {
  if (!job || job.stage === "queued") return 0;
  const startedAt = "execution_started_at" in job
    ? job.execution_started_at
    : job.started_at ?? fallbackStartedAt;
  if (startedAt == null) return 0;
  const endedAt = job.done || job.interrupted
    ? job.finished_at ?? job.updated_at ?? startedAt
    : now;
  return Math.max(0, Math.floor(endedAt - startedAt));
};

export const queueItemClass = job => {
  if (job?.canceled || job?.stage === "canceled") return "canceled";
  if (job?.error) return "error";
  if (job?.interrupted || job?.stage === "interrupted") return "interrupted";
  if (job?.done) return "done";
  if (!job?.stage || job.stage === "queued") return "queued";
  return "running";
};
