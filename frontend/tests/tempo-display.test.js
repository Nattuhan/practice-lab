import assert from 'node:assert/strict';
import test from 'node:test';
import { tempoAtTime, tempoRange, meterAtTime } from '../src/tempo-display.js';

test('再生位置のテンポを表示し、遅い前半と速い後半の両方を示す', () => {
  const beats = [...Array.from({length: 41}, (_, i) => i * .8), ...Array.from({length: 80}, (_, i) => 32 + (i + 1) * .375)];
  const data = { tempoMode: 'variable', bpm: 160, beats };
  assert.ok(Math.abs(tempoAtTime(data, 1) - 75) < .01);
  assert.ok(Math.abs(tempoAtTime(data, 31) - 75) < .01);
  assert.ok(Math.abs(tempoAtTime(data, 32) - 160) < .01);
  assert.ok(Math.abs(tempoAtTime(data, 45) - 160) < .01);
  assert.deepEqual(tempoRange(data), [75, 160]);
  assert.equal(tempoAtTime({...data, tempoMode: 'constant'}, 1), 160);
});

test('現在の小節頭に従って3拍子と4拍子を表示する', () => {
  const beats = Array.from({length: 30}, (_, i) => i * .5);
  const data = {beats, downbeats: [0,2,4,6,7.5,9,10.5,12]};
  assert.equal(meterAtTime(data, 3), 4);
  assert.equal(meterAtTime(data, 6), 3);
  assert.equal(meterAtTime(data, 10), 3);
});
