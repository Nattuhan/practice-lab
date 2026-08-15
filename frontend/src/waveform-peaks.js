export const extractWaveformPeaks = (audioBuffer, width) => {
  const pixelCount = Math.max(1, Math.floor(width));
  const channels = Number(audioBuffer?.numberOfChannels || 0);
  const samples = Number(audioBuffer?.length || 0);
  if (!channels || !samples || typeof audioBuffer.getChannelData !== "function") return new Float32Array(pixelCount);

  const channelData = Array.from({ length: channels }, (_, index) => audioBuffer.getChannelData(index));
  const peaks = new Float32Array(pixelCount);
  let strongest = 0;
  for (let pixel = 0; pixel < pixelCount; pixel += 1) {
    const start = Math.floor(pixel / pixelCount * samples);
    const end = Math.max(start + 1, Math.floor((pixel + 1) / pixelCount * samples));
    const step = Math.max(1, Math.floor((end - start) / 96));
    let peak = 0;
    for (let sample = start; sample < end; sample += step) {
      for (const data of channelData) peak = Math.max(peak, Math.abs(data[sample] || 0));
    }
    peaks[pixel] = peak;
    strongest = Math.max(strongest, peak);
  }
  if (strongest > 0) {
    for (let index = 0; index < peaks.length; index += 1) peaks[index] /= strongest;
  }
  return peaks;
};
