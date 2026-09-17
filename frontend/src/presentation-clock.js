const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
export const normalizeSyncSettings = (input = {}) => ({
  mode: ["auto", "manual", "off"].includes(input?.mode) ? input.mode : "auto",
  manualMs: clamp(Number(input?.manualMs) || 0, 0, 1000),
  adjustmentMs: clamp(Number(input?.adjustmentMs) || 0, -250, 250),
});

export function outputDelaySeconds(context, nowMs) {
  if (!context || context.state !== "running") return null;
  const timestamp = context.getOutputTimestamp?.();
  if (timestamp?.contextTime > 0 && timestamp.performanceTime > 0
      && nowMs >= timestamp.performanceTime && nowMs - timestamp.performanceTime < 1000) {
    const outputTime = timestamp.contextTime + (nowMs - timestamp.performanceTime) / 1000;
    const delay = context.currentTime - outputTime;
    if (Number.isFinite(delay) && delay > 0 && delay <= 1) return delay;
  }
  const latency = context.outputLatency;
  if (!Number.isFinite(latency) || latency <= 0 || latency > 1) return null;
  // outputLatency excludes the browser's audio graph buffer. Do not add it
  // again when using the already correlated output timestamp above.
  return clamp(latency + (Number(context.baseLatency) || 0), 0, 1);
}

export function correctionSeconds(settings, transport, measuredDelay) {
  const value = normalizeSyncSettings(settings);
  if (transport === "builtin" || value.mode === "off") return 0;
  if (value.mode === "manual") return value.manualMs / 1000;
  if (transport !== "bluetooth" || measuredDelay === null) return 0;
  return clamp(measuredDelay + value.adjustmentMs / 1000, 0, 1);
}

// Delay presentation, never the transport. History handles rate changes and
// loop discontinuities that `currentTime - latency * rate` cannot represent.
export class PresentationClock {
  points = [];
  segment = 0;
  reset(now, time) { this.points = [{ now, time, playing: false, rate: 1, jump: true, segment: ++this.segment }]; }
  record({ now, time, playing, rate = 1, jump = false }) {
    const last = this.points.at(-1);
    if (last && now < last.now) this.points = [];
    const elapsed = last ? (now - last.now) / 1000 : 0;
    const expected = last?.playing ? elapsed * last.rate : 0;
    const discontinuity = jump || !!last && Math.abs(time - last.time - expected) > 0.12;
    if (discontinuity) this.segment++;
    this.points.push({ now, time, playing, rate, jump: discontinuity, segment: this.segment });
    while (this.points.length > 2 && this.points[1].now < now - 1500) this.points.shift();
  }
  read(now, delay) {
    const target = now - delay * 1000;
    const first = this.points[0];
    if (!first) return { time: 0, playing: false, rate: 1 };
    if (target < first.now) return { ...first, playing: false };
    for (let i = this.points.length - 1; i >= 0; i--) {
      const a = this.points[i], b = this.points[i + 1];
      if (a.now > target) continue;
      if (!b || b.jump || b.now === a.now) return a;
      const fraction = (target - a.now) / (b.now - a.now);
      return { ...a, time: a.time + (b.time - a.time) * fraction };
    }
    return first;
  }
}

// WaveSurfer 7.12's renderer is isolated here: setTime/seekTo would also seek
// the audio. Rendering progress only leaves media time and loop events intact.
export function renderPresentationProgress(wave, time) {
  const duration = wave.getDuration();
  if (duration > 0) wave.renderer.renderProgress(clamp(time / duration, 0, 1), wave.isPlaying());
}
