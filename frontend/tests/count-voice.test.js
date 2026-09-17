import test from 'node:test';
import assert from 'node:assert/strict';
import { beatCounts, countVoiceSamples } from '../src/count-voice.js';
import { alignedWav } from '../src/aligned-click.js';

test('4拍・2拍・4拍で小節頭から読み上げ直す', () => {
  const beats = Array.from({ length: 14 }, (_, i) => .17 + i * .36);
  const counts = beatCounts(beats, [beats[0], beats[4], beats[6], beats[10]]);
  assert.deepEqual(counts, [1,2,3,4,1,2,1,2,3,4,1,2,3,4]);
  // A partial loop starts at its actual beat number, not a new arbitrary one.
  assert.deepEqual(counts.slice(3, 9), [4,1,2,1,2,3]);
});

test('読み上げ音声は楽曲と独立した同期チャンネルに収録する', async () => {
  const sampleRate = 8000, length = 16000;
  const original = { sampleRate, length, numberOfChannels: 1, getChannelData: () => new Float32Array(length) };
  const beats = [.1,.5,.9,1.3,1.7], counts = [1,2,1,2,3];
  const blob = await alignedWav(original, beats, { counts });
  const bytes = await blob.arrayBuffer(), view = new DataView(bytes), pcm = new Float32Array(bytes,44);
  assert.equal(view.getUint16(22,true),4);
  const voices = countVoiceSamples(sampleRate);
  for (let index = 0; index < beats.length; index++) {
    const start = Math.round(beats[index] * sampleRate), word = voices[counts[index]];
    for (let k = 50; k < Math.min(word.length - 50, length - start); k++) {
      assert.equal(pcm[(start+k)*4+3],word[k]);
      assert.equal(pcm[(start+k)*4],0);
    }
  }
});
