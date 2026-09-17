import test from 'node:test';
import assert from 'node:assert/strict';
import { PresentationClock, correctionSeconds, outputDelaySeconds, normalizeSyncSettings } from '../src/presentation-clock.js';

test('automatic correction requires active Bluetooth; builtin remains uncorrected even in manual mode', () => {
  for (const transport of ['builtin', 'other', 'unknown']) assert.equal(correctionSeconds({}, transport, .28), 0);
  assert.equal(correctionSeconds({}, 'bluetooth', .28), .28);
  assert.equal(correctionSeconds({}, 'bluetooth', null), 0);
  assert.equal(correctionSeconds({ mode: 'off' }, 'bluetooth', .28), 0);
  assert.equal(correctionSeconds({ mode: 'manual', manualMs: 300 }, 'builtin', .28), 0);
  assert.equal(correctionSeconds({ mode: 'manual', manualMs: 300 }, 'unknown', null), .3);
  assert.equal(correctionSeconds({ adjustmentMs: -50 }, 'bluetooth', .28).toFixed(2), '0.23');
  assert.equal(normalizeSyncSettings({ manualMs: Infinity }).manualMs, 1000);
});

test('timestamp and fallback estimates do not double-count latency; invalid reports do not enable correction', () => {
  const ctx = { state: 'running', currentTime: 12, baseLatency: .006, outputLatency: .3,
    getOutputTimestamp: () => ({ contextTime: 11.7, performanceTime: 9900 }) };
  assert.ok(Math.abs(outputDelaySeconds(ctx, 10000) - .2) < 1e-8);
  ctx.getOutputTimestamp = () => ({ contextTime: 0, performanceTime: 0 });
  assert.equal(outputDelaySeconds(ctx, 10000), .306);
  ctx.outputLatency = NaN;
  assert.equal(outputDelaySeconds(ctx, 10000), null);
  ctx.state = 'suspended';
  assert.equal(outputDelaySeconds(ctx, 10000), null);
});

test('presentation follows the delayed timeline across speed changes, pauses, resume and loop jumps', () => {
  const clock = new PresentationClock();
  clock.reset(0, 5);
  clock.record({ now: 0, time: 5, playing: true });
  clock.record({ now: 500, time: 5.5, playing: true });
  clock.record({ now: 1000, time: 6, playing: true, rate: .5 });
  clock.record({ now: 1500, time: 6.25, playing: true, rate: .5 });
  assert.equal(clock.read(1500, .75).time, 5.75); // old 1x speed is still audible
  assert.equal(clock.read(1500, .25).time, 6.125);
  clock.record({ now: 1600, time: 6.3, playing: false, rate: .5 });
  clock.record({ now: 1800, time: 6.3, playing: false, rate: .5 });
  assert.equal(clock.read(1800, .3).playing, true); // output queue still drains
  clock.record({ now: 2000, time: 6.3, playing: true, rate: .5 });
  assert.equal(clock.read(2000, .3).playing, false);
  clock.record({ now: 2200, time: 6.4, playing: true, rate: .5 });
  clock.record({ now: 2200, time: 2, playing: false, rate: .5, jump: true });
  clock.record({ now: 2300, time: 2, playing: true, rate: .5 });
  clock.record({ now: 2500, time: 2.1, playing: true, rate: .5 });
  assert.equal(clock.read(2500, .4).time, 6.35); // previous loop, not an invented 1.9s
  assert.equal(clock.read(2500, .1).time, 2.05);
});

test('manual seeking immediately resets display; startup and stalls hold the chosen position', () => {
  const clock = new PresentationClock();
  clock.reset(1000, 20);
  assert.equal(clock.read(1000, .3).time, 20);
  assert.equal(clock.read(1000, .3).playing, false);
  clock.record({ now: 1100, time: 20, playing: true });
  clock.record({ now: 1200, time: 20.1, playing: false });
  clock.record({ now: 1400, time: 20.1, playing: false });
  assert.equal(clock.read(1400, .1).time, 20.1);
  clock.reset(1500, 2);
  assert.equal(clock.read(1500, .3).time, 2);
});

test('Bluetooth startup does not advance video while the supposedly playing source clock is frozen', () => {
  const clock = new PresentationClock();
  clock.reset(0, 0);
  for (let now = 10; now <= 500; now += 10) {
    clock.record({ now, time: 0, playing: true });
    assert.equal(clock.read(now, 0).playing, false);
    assert.equal(clock.read(now, .28).playing, false);
  }
  // A single audio quantum can arrive before a second hardware startup wait.
  for (let now = 510; now <= 800; now += 10) clock.record({ now, time: .006, playing: true });
  assert.equal(clock.read(800, .2).playing, false);
  for (let now = 810; now <= 1300; now += 10) clock.record({ now, time: .006 + (now - 800) / 1000, playing: true });
  assert.equal(clock.read(1300, .28).playing, true);
  assert.ok(Math.abs(clock.read(1300, .28).time - .226) < 1e-8);
});
