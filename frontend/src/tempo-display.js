const median = values => {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};
const indexAt = (times, time) => {
  let left = 0, right = times.length;
  while (left < right) {
    const middle = (left + right) >>> 1;
    if (times[middle] <= time) left = middle + 1; else right = middle;
  }
  return Math.max(0, left - 1);
};

export const tempoAtTime = (data, time) => {
  const beats = data?.beats || [];
  if (data?.tempoMode !== 'variable' || beats.length < 2) return Number(data?.bpm || 0);
  const index = Math.min(beats.length - 2, indexAt(beats, time));
  const period = beats[index + 1] - beats[index];
  // Smooth detector jitter within the local pulse, without averaging across
  // a genuine tempo change into a BPM that neither passage actually plays.
  const gaps = [];
  for (let i = Math.max(0, index - 4); i <= Math.min(beats.length - 2, index + 4); i++) {
    const gap = beats[i + 1] - beats[i];
    if (gap > 0 && Math.abs(gap / period - 1) < .15) gaps.push(gap);
  }
  return gaps.length ? 60 / median(gaps) : Number(data?.bpm || 0);
};

export const tempoRange = data => {
  if (data?.tempoMode !== 'variable' || (data.beats?.length || 0) < 8) return null;
  const values = [];
  for (let i = 0; i < data.beats.length - 1; i += 8) values.push(tempoAtTime(data, data.beats[i]));
  const sorted = values.filter(value => value > 0).sort((a, b) => a - b);
  if (!sorted.length) return null;
  // A single pickup or missed detection is not a tempo region.
  const low = sorted[Math.floor((sorted.length - 1) * .05)];
  const high = sorted[Math.ceil((sorted.length - 1) * .95)];
  return high / low > 1.1 ? [Math.round(low), Math.round(high)] : null;
};

export const meterAtTime = (data, time) => {
  const beats = data?.beats || [], heads = data?.downbeats || [];
  if (heads.length < 2 || beats.length < 2) return null;
  const index = Math.min(heads.length - 2, indexAt(heads, time));
  const start = indexAt(beats, heads[index] + .001);
  const end = indexAt(beats, heads[index + 1] + .001);
  const meter = end - start;
  return meter >= 2 && meter <= 12 ? meter : null;
};
