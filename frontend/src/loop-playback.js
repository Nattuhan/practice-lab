// Media backends can report a slightly earlier time immediately after a seek,
// especially below 1x. Without this tolerance that rounding error seeks to the
// loop start again on every timeupdate and playback never advances.
export const LOOP_START_TOLERANCE_SECONDS = 0.1;
export const MIN_CUSTOM_LOOP_SECONDS = 0.1;

/**
 * Clamp a dragged loop to the media duration.
 * Very short ranges are treated as accidental clicks instead of playable loops.
 */
export const clampCustomLoopRange = (start, end, duration) => {
  const mediaDuration = Number(duration);
  const rangeStart = Number(start);
  const rangeEnd = Number(end);
  if (!(mediaDuration > 0) || !Number.isFinite(rangeStart) || !Number.isFinite(rangeEnd)) return null;
  const clampedStart = Math.min(mediaDuration, Math.max(0, rangeStart));
  const clampedEnd = Math.min(mediaDuration, Math.max(clampedStart, rangeEnd));
  if (clampedEnd - clampedStart < MIN_CUSTOM_LOOP_SECONDS) return null;
  return { start: clampedStart, end: clampedEnd, kind: "custom" };
};

/** Move a custom loop without changing its length, pinning it at media edges. */
export const moveCustomLoopRange = (range, delta, duration) => {
  const rangeDuration = range.end - range.start;
  if (!(rangeDuration > 0) || !(duration > 0) || !Number.isFinite(delta)) return null;
  const start = Math.min(
    Math.max(0, range.start + delta),
    Math.max(0, duration - rangeDuration),
  );
  return { start, end: start + rangeDuration, kind: "custom" };
};

export const shouldRestartLoop = (time, range) => {
  if (!range || !Number.isFinite(time)) return false;
  const start = Number(range.start);
  const end = Number(range.end);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return false;
  return time < start - LOOP_START_TOLERANCE_SECONDS || time >= end;
};
