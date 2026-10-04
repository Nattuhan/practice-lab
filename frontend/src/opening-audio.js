// Locate audible source material, not the detector's first beat: a quiet vocal
// pickup can precede every reported beat. Use channel power so opposite stereo
// phases cannot hide it, and scale the threshold to the established music.
export const audibleOpeningStart = (buffer, firstBeat, period) => {
  if (!(firstBeat > 0 && Number.isFinite(firstBeat) && period > 0 && Number.isFinite(period))) return null;
  const { sampleRate, length, numberOfChannels } = buffer;
  const planes = Array.from({ length: numberOfChannels }, (_, i) => buffer.getChannelData(i));
  const frame = Math.max(1, Math.round(sampleRate * Math.min(.02, period / 16)));
  const limit = Math.min(length, Math.ceil((firstBeat + 8 * period) * sampleRate));
  const levels = [];
  for (let start = 0; start < limit; start += frame) {
    const end = Math.min(limit, start + frame);
    let power = 0;
    for (const plane of planes) {
      for (let i = start; i < end; i++) power += plane[i] ** 2;
    }
    levels.push(Math.sqrt(power / ((end - start) * numberOfChannels)));
  }
  const reference = levels.slice(Math.floor(firstBeat * sampleRate / frame)).sort((a, b) => a - b);
  if (!reference.length) return null;
  const threshold = Math.max(1e-4, reference[Math.floor((reference.length - 1) * .75)] * .03);
  const first = levels.findIndex(level => level > threshold);
  return first < 0 ? null : first * frame / sampleRate;
};
