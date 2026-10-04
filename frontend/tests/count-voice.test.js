import test from 'node:test';
import assert from 'node:assert/strict';
import { VOICE_PITCH_IDS, beatCounts, completeOpeningClickBar, countVoiceSamples, normalizeVoicePitch } from '../src/count-voice.js';
import { alignedWav } from '../src/aligned-click.js';

test('4拍・2拍・4拍で小節頭から読み上げ直す', () => {
  const beats = Array.from({ length: 14 }, (_, i) => .17 + i * .36);
  const counts = beatCounts(beats, [beats[0], beats[4], beats[6], beats[10]]);
  assert.deepEqual(counts, [1,2,3,4,1,2,1,2,3,4,1,2,3,4]);
  // A partial loop starts at its actual beat number, not a new arbitrary one.
  assert.deepEqual(counts.slice(3, 9), [4,1,2,1,2,3]);
});

test('一定BPMの4拍・3拍・4拍を、途中からのループでも拍番号どおりに読む', () => {
  const beats = Array.from({ length: 15 }, (_, i) => .23 + i * .49177);
  const counts = beatCounts(beats, [beats[0], beats[4], beats[7], beats[11]]);
  assert.deepEqual(counts, [1,2,3,4,1,2,3,1,2,3,4,1,2,3,4]);
  assert.deepEqual(counts.slice(5, 11), [2,3,1,2,3,4]);
});

test('最初の小節頭より前のボーカルピックアップも確定した拍子で逆算する', () => {
  const beats = Array.from({ length: 14 }, (_, i) => .11 + i * .33);
  assert.deepEqual(
    beatCounts(beats, [beats[6], beats[10]]),
    [3,4,1,2,3,4,1,2,3,4,1,2,3,4],
  );
  // The same rule follows a measured two-beat opening bar instead of assuming 4/4.
  assert.deepEqual(
    beatCounts(beats, [beats[3], beats[5], beats[9]]).slice(0, 6),
    [2,1,2,1,2,1],
  );
  // One isolated head does not establish a meter for the preceding audio.
  assert.deepEqual(beatCounts(beats.slice(0, 5), [beats[3]]), [0,0,0,1,2]);
});

test('3・4から始まる曲は空白に1・2だけを補い、曲中の拍と小節を保つ', () => {
  for (const [period, offset] of [[.33, 2.47], [.49, 3.51], [.68, 4.85]]) {
    const beats = Array.from({ length: 18 }, (_, i) => offset + i * period);
    const heads = [beats[2], beats[6], beats[10], beats[12], beats[16]];
    const counts = beatCounts(beats, heads);
    const completed = completeOpeningClickBar(beats, heads);
    assert.equal(completed.length, beats.length + 2);
    assert.ok(Math.abs(completed[0] - (offset - 2 * period)) < 1e-6);
    assert.ok(Math.abs(completed[1] - (offset - period)) < 1e-6);
    assert.deepEqual(completed.slice(2), beats);
    assert.deepEqual(beatCounts(completed, heads), [1, 2, ...counts]);
    assert.deepEqual(completeOpeningClickBar(completed, heads), completed);
  }
});

test('冒頭の補完は確定した拍子とファイル内の空白に従い、余分な小節を足さない', () => {
  const beats = Array.from({ length: 14 }, (_, i) => 3 + i * .5);
  const threeHeads = [beats[1], beats[4], beats[7]];
  assert.deepEqual(completeOpeningClickBar(beats, threeHeads), [2, 2.5, ...beats]);
  assert.deepEqual(beatCounts(completeOpeningClickBar(beats, threeHeads), threeHeads).slice(0, 4), [1, 2, 3, 1]);
  const twoHeads = [beats[1], beats[3], beats[5]];
  assert.deepEqual(completeOpeningClickBar(beats, twoHeads), [2.5, ...beats]);
  const nearStart = beats.map(time => time - 2.6), heads = [nearStart[2], nearStart[6]];
  assert.deepEqual(completeOpeningClickBar(nearStart, heads), nearStart);
  const partial = beats.map(time => time - 2.4), partialHeads = [partial[2], partial[6]];
  const completed = completeOpeningClickBar(partial, partialHeads);
  assert.equal(completed.length, partial.length + 1);
  assert.ok(Math.abs(completed[0] - .1) < 1e-6);
  assert.deepEqual(beatCounts(completed, partialHeads).slice(0, 4), [2, 3, 4, 1]);
  const atZero = beats.map(time => time - 2);
  assert.equal(completeOpeningClickBar(atZero, [atZero[2], atZero[6]])[0], 0);
  assert.equal(completeOpeningClickBar(beats, [beats[0], beats[4]]), beats);
  assert.equal(completeOpeningClickBar(beats, [beats[4], beats[8]]), beats);
});

test('拍子不明・冒頭のテンポ変化・拍列と合わない小節頭は補完しない', () => {
  const beats = Array.from({ length: 14 }, (_, i) => 3 + i * .5);
  assert.equal(completeOpeningClickBar(beats, []), beats);
  assert.equal(completeOpeningClickBar(beats, [beats[2]]), beats);
  assert.equal(completeOpeningClickBar(beats, [beats[2] + .2, beats[6] + .2]), beats);
  const freeIntro = [.5, 2, ...beats.slice(2)];
  assert.equal(completeOpeningClickBar(freeIntro, [freeIntro[2], freeIntro[6]]), freeIntro);
  const change = [2.8, 3.4, ...beats.slice(2)];
  assert.equal(completeOpeningClickBar(change, [change[2], change[6]]), change);
});

test('補った1・2は無音の元音源と別のクリック・読み上げチャンネルに入る', async () => {
  const sampleRate = 8000, length = 64000;
  const music = Float32Array.from({ length }, (_, i) => i >= 24000 ? .2 : 0);
  const original = { sampleRate, length, numberOfChannels: 1, getChannelData: () => music };
  const detected = Array.from({ length: 8 }, (_, i) => 3 + i * .5);
  const heads = [4, 6], beats = completeOpeningClickBar(detected, heads);
  const blob = await alignedWav(original, beats, { counts: beatCounts(beats, heads) });
  const pcm = new Float32Array(await blob.arrayBuffer(), 44);
  for (let i = 0; i < length; i++) assert.equal(pcm[i * 4], music[i]);
  const voices = countVoiceSamples(sampleRate);
  for (const [time, count] of [[2, 1], [2.5, 2], [3, 3], [3.5, 4]]) {
    const start = Math.round(time * sampleRate), word = voices[count];
    assert.ok(pcm.slice(start * 4, (start + 400) * 4).some((value, i) => i % 4 === 2 && Math.abs(value) > .01));
    for (let k = 50; k < word.length - 50; k++) assert.equal(pcm[(start + k) * 4 + 3], word[k]);
  }
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

test('高めの読み上げは専用音声を同期チャンネルへ収録する', async () => {
  const sampleRate = 8000, length = 8000;
  const original = { sampleRate, length, numberOfChannels: 1, getChannelData: () => new Float32Array(length) };
  const normal = countVoiceSamples(sampleRate)[1];
  const high = countVoiceSamples(sampleRate, 'high')[1];
  assert.notDeepEqual([...high.slice(0, 1000)], [...normal.slice(0, 1000)]);
  assert.deepEqual(VOICE_PITCH_IDS, ['standard', 'high']);
  assert.equal(normalizeVoicePitch('unknown'), 'standard');
  const blob = await alignedWav(original, [.1], { counts: [1], voicePitch: 'high' });
  const pcm = new Float32Array(await blob.arrayBuffer(), 44);
  const start = Math.round(.1 * sampleRate);
  for (let k = 50; k < high.length - 50; k++) assert.equal(pcm[(start + k) * 4 + 3], high[k]);
});
