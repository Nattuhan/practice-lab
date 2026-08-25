export const LOOP_START_TOLERANCE_SECONDS = 0.1;

export const shouldRestartLoop = (time, range) => {
  if (!range || !Number.isFinite(time)) return false;
  const start = Number(range.start);
  const end = Number(range.end);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return false;
  return time < start - LOOP_START_TOLERANCE_SECONDS || time >= end;
};
