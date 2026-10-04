import voiceData from '../../practice_lab/assets/count_voice.json' with { type: 'json' };
import highVoiceData from '../../practice_lab/assets/count_voice_high.json' with { type: 'json' };

const barHeadIndexes = (beats, downbeats) => {
  const heads = new Set();
  for (const head of downbeats || []) {
    let best = -1;
    for (let i = 0; i < beats.length; i++) {
      if (best < 0 || Math.abs(beats[i] - head) < Math.abs(beats[best] - head)) best = i;
    }
    if (best >= 0) heads.add(best);
  }
  return [...heads].sort((a, b) => a - b);
};

// Complete only the bar containing the first detected beat. Silence can hold
// its count-in, but is not evidence for adding earlier bars to the analysis.
export const completeOpeningClickBar = (beats, downbeats) => {
  const [firstHead, secondHead] = barHeadIndexes(beats, downbeats);
  const barLength = secondHead - firstHead;
  if (!(barLength >= 2 && barLength <= 12)) return beats;
  const missing = (barLength - firstHead % barLength) % barLength;
  if (!missing) return beats;
  const period = (beats[secondHead] - beats[firstHead]) / barLength;
  if (!(period > 0 && Number.isFinite(period))) return beats;
  // A pickup must share the opening bar's pulse. Do not extrapolate a free-time
  // introduction, a tempo transition, or bar heads that miss the beat grid.
  if ((downbeats || []).slice(0, 2).some(head =>
    Math.min(...[firstHead, secondHead].map(index => Math.abs(beats[index] - head))) > period * .12)) return beats;
  for (let i = 1; i <= secondHead; i++) {
    const gap = (beats[i] - beats[i - 1]) / period;
    if (!Number.isFinite(gap) || Math.abs(gap - 1) > .1) return beats;
  }
  const prefix = Array.from({ length: missing }, (_, i) => beats[0] - (missing - i) * period)
    .filter(time => time >= -.0000005)
    .map(time => Math.max(0, Math.round(time * 1e6) / 1e6));
  return prefix.length ? [...prefix, ...beats] : beats;
};

// Reset at measured bar heads, never at index % 4: a two-beat bar is 1, 2,
// followed by 1 at the next bar. Seeking/looping therefore needs no counter state.
export const beatCounts = (beats, downbeats) => {
  const headIndexes = barHeadIndexes(beats, downbeats);
  const heads = new Set(headIndexes);
  const firstHead = headIndexes[0];
  const openingBarLength = headIndexes.length >= 2 ? headIndexes[1] - firstHead : 0;
  let count = 0;
  return beats.map((_, index) => {
    if (heads.has(index)) count = 1;
    // A vocal pickup can begin before the first detected bar head. Once two
    // measured heads establish that opening bar's length, count its preceding
    // beats backwards so spoken clicks cover the pickup as well.
    else if (index < firstHead && openingBarLength >= 2 && openingBarLength <= 12) {
      count = ((index - firstHead) % openingBarLength + openingBarLength) % openingBarLength + 1;
    }
    else if (count) count++;
    return count <= 12 ? count : 0;
  });
};

const cache = new Map();
export const VOICE_PITCH_IDS = Object.freeze(['standard', 'high']);
export const normalizeVoicePitch = value => VOICE_PITCH_IDS.includes(value) ? value : 'standard';
export const countVoiceSamples = (sampleRate, variant = 'standard') => {
  const pitch = normalizeVoicePitch(variant);
  const data = pitch === 'high' ? highVoiceData : voiceData;
  const cacheKey = `${pitch}:${sampleRate}`;
  if (!cache.has(cacheKey)) {
    const voices = {};
    for (const [number, encoded] of Object.entries(data.samples)) {
      const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
      const view = new DataView(bytes.buffer);
      const length = bytes.length / 2;
      voices[number] = Float32Array.from({ length: Math.ceil(length * sampleRate / data.sampleRate) }, (_, i) => {
        const position = i * data.sampleRate / sampleRate;
        const left = Math.floor(position), fraction = position - left;
        const a = view.getInt16(Math.min(left, length - 1) * 2, true);
        const b = view.getInt16(Math.min(left + 1, length - 1) * 2, true);
        return (a + (b - a) * fraction) / 32768;
      });
    }
    cache.set(cacheKey, voices);
  }
  return cache.get(cacheKey);
};
