import voiceData from '../../practice_lab/assets/count_voice.json' with { type: 'json' };

// Reset at measured bar heads, never at index % 4: a two-beat bar is 1, 2,
// followed by 1 at the next bar. Seeking/looping therefore needs no counter state.
export const beatCounts = (beats, downbeats) => {
  const heads = new Set();
  for (const head of downbeats || []) {
    let best = -1;
    for (let i = 0; i < beats.length; i++) {
      if (best < 0 || Math.abs(beats[i] - head) < Math.abs(beats[best] - head)) best = i;
    }
    if (best >= 0) heads.add(best);
  }
  let count = 0;
  return beats.map((_, index) => {
    if (heads.has(index)) count = 1;
    else if (count) count++;
    return count <= 12 ? count : 0;
  });
};

const cache = new Map();
export const countVoiceSamples = sampleRate => {
  if (!cache.has(sampleRate)) {
    const voices = {};
    for (const [number, encoded] of Object.entries(voiceData.samples)) {
      const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
      const view = new DataView(bytes.buffer);
      const length = bytes.length / 2;
      voices[number] = Float32Array.from({ length: Math.ceil(length * sampleRate / voiceData.sampleRate) }, (_, i) => {
        const position = i * voiceData.sampleRate / sampleRate;
        const left = Math.floor(position), fraction = position - left;
        const a = view.getInt16(Math.min(left, length - 1) * 2, true);
        const b = view.getInt16(Math.min(left + 1, length - 1) * 2, true);
        return (a + (b - a) * fraction) / 32768;
      });
    }
    cache.set(sampleRate, voices);
  }
  return cache.get(sampleRate);
};
