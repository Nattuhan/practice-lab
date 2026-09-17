// Hardware-backed presentation audit. Runs the real desktop IPC and frontend
// in an isolated profile; latency is never mocked and test media is silent.
import { _electron as electron, expect } from '@playwright/test';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
import { silentWav, baselineSession, baselineResult } from '../tests/e2e/fixtures.js';
const require = createRequire(import.meta.url);
const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = fs.mkdtempSync(path.join(os.tmpdir(), 'practice-lab-presentation-'));
const profile = path.join(output, 'profile');
fs.mkdirSync(profile);
fs.writeFileSync(path.join(profile, 'settings.json'), JSON.stringify({ autoUpdate: false, cloud: { enabled: false } }));
const moviePath = path.join(output, 'clock.mp4');
execFileSync(require('ffmpeg-static'), ['-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30',
  '-t', '12', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', moviePath]);
const movie = fs.readFileSync(moviePath), wav = silentWav(12, 44100);
const executablePath = process.env.PRACTICE_LAB_AUDIT_APP || require('electron');
const args = process.env.PRACTICE_LAB_AUDIT_APP ? [`--user-data-dir=${profile}`] : [repository, `--user-data-dir=${profile}`];
const app = await electron.launch({ executablePath, args, cwd: repository,
  env: { ...process.env, PYTHONPATH: repository }, timeout: 60000 });
const errors = [], summary = [];
try {
  assert.equal(fs.realpathSync(await app.evaluate(({ app }) => app.getPath('userData'))), fs.realpathSync(profile), 'Audit must not use the normal app profile');
  const page = await app.firstWindow();
  page.on('pageerror', error => errors.push(error.message));
  await page.waitForURL('http://127.0.0.1:*/', { timeout: 60000 });
  await page.route('**/results/manifest.json', route => route.fulfill({ json: [baselineSession] }));
  await page.route('**/results/e2e-baseline.json', route => route.fulfill({ json: {
    ...baselineResult, duration: 12, beats: Array.from({ length: 24 }, (_, i) => i / 2),
    sections: [{ ...baselineResult.sections[0], start_time: 2, end_time: 4.7 }],
  } }));
  const mediaResponse = (route, bytes, type) => {
    const range = route.request().headers().range?.match(/bytes=(\d+)-(\d*)/);
    if (!range) return route.fulfill({ contentType: type, headers: { 'accept-ranges': 'bytes' }, body: bytes });
    const start = Number(range[1]), end = range[2] ? Math.min(Number(range[2]), bytes.length - 1) : bytes.length - 1;
    return route.fulfill({ status: 206, contentType: type, headers: {
      'accept-ranges': 'bytes', 'content-range': `bytes ${start}-${end}/${bytes.length}`,
    }, body: bytes.subarray(start, end + 1) });
  };
  await page.route('**/audio/e2e-baseline.mp3', route => mediaResponse(route, wav, 'audio/wav'));
  await page.route('**/stems/e2e-baseline/*', route => mediaResponse(route, wav, 'audio/wav'));
  await page.route('**/video/**', route => mediaResponse(route, movie, 'video/mp4'));
  await page.route('**/results/*/library', route => route.fulfill({ json: { tags: [] } }));
  await page.addInitScript(() => {
    window.__presentationAudit = { ctx: null, media: null, startup: [] };
    const traceStarted = performance.now();
    const traceTimer = setInterval(() => {
      const p = window.__presentationAudit;
      if (p.ctx && p.media) p.startup.push({ at: performance.now(), time: p.media.currentTime,
        ctxTime: p.ctx.currentTime, state: p.ctx.state, paused: p.media.paused,
        video: document.querySelector('#video-player').currentTime,
        view: Number(document.querySelector('#time-cur').dataset.seconds) });
      if (performance.now() - traceStarted > 6000) clearInterval(traceTimer);
    }, 10);
    const create = AudioContext.prototype.createMediaElementSource;
    AudioContext.prototype.createMediaElementSource = function (media) {
      window.__presentationAudit.ctx = this;
      window.__presentationAudit.media = media;
      return create.call(this, media);
    };
  });
  await page.reload();
  await expect(page.locator('#btn-play')).toBeVisible();
  await expect(page.locator('#btn-play')).toBeEnabled();
  const device = await page.evaluate(() => window.practiceLabDesktop.getAudioOutput());
  assert.equal(device.transport, 'bluetooth', 'Connect a Bluetooth device and choose it as the active output before running this audit');
  console.log(JSON.stringify({ output, device }));
  await page.locator('#btn-play').click();
  await expect(page.locator('#bluetooth-sync-status')).toBeVisible();
  const sample = async (label, duration) => {
    const points = await page.evaluate(async duration => {
      const points = [], started = performance.now();
      await new Promise(resolve => {
        const tick = () => {
          const { ctx, media } = window.__presentationAudit, video = document.querySelector('#video-player');
          points.push({ at: performance.now(), audio: media.currentTime, view: Number(document.querySelector('#time-cur').dataset.seconds),
            video: video.currentTime, seeking: video.seeking || media.seeking, rate: media.playbackRate,
            outputLatency: ctx.outputLatency, baseLatency: ctx.baseLatency, contextTime: ctx.currentTime,
            timestamp: ctx.getOutputTimestamp(), paused: media.paused });
          if (performance.now() - started < duration) requestAnimationFrame(tick); else resolve();
        };
        tick();
      });
      return points;
    }, duration);
    fs.writeFileSync(path.join(output, `${label}.json`), JSON.stringify(points));
    fs.writeFileSync(path.join(output, 'startup.json'), JSON.stringify(await page.evaluate(() => window.__presentationAudit.startup)));
    const jumps = points.filter((p, i) => i && p.view < points[i - 1].view - .5);
    const stable = points.filter(p => p.at - points[0].at > 800 && !p.seeking
      && jumps.every(jump => Math.abs(p.at - jump.at) > 250));
    assert.ok(stable.length > 30, `${label}: not enough stable samples`);
    const videoErrors = stable.map(p => Math.abs(p.video - p.view));
    const linear = stable.filter(p => p.audio >= p.view && p.audio - p.view < 1);
    const offsets = linear.map(p => (p.audio - p.view) / p.rate);
    const median = values => values.toSorted((a, b) => a - b)[Math.floor(values.length / 2)];
    const row = { label, samples: points.length, wraps: jumps.length,
      outputLatencyMs: Math.round(median(stable.map(p => p.outputLatency)) * 1000),
      displayDelayMs: Math.round(median(offsets) * 1000), maximumVideoErrorMs: Math.round(Math.max(...videoErrors) * 1000) };
    summary.push(row); console.log(JSON.stringify(row));
    assert.ok(row.maximumVideoErrorMs < 150, `${label}: video and display clocks diverged`);
    assert.ok(row.displayDelayMs > 50 && row.displayDelayMs < 1000, `${label}: hardware correction did not engage`);
    assert.ok(Math.abs(row.displayDelayMs - row.outputLatencyMs) < 80, `${label}: display delay differs from hardware estimate`);
    if (label.includes('loop')) assert.ok(jumps.length >= 2, 'Loop transitions were not exercised');
  };
  await sample('normal', 3500);
  await page.locator('#playback-rate').evaluate(el => { el.value = '0.50'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  await sample('half-speed', 3500);
  await page.locator('#playback-rate').evaluate(el => { el.value = '0.75'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.locator('#btn-loop').click();
  await page.getByRole('button', { name: '曲構成', exact: true }).click();
  await page.locator('.sec-row').first().click();
  await sample('loop-075', 11000);
  await page.locator('#bluetooth-sync-status').hover();
  await page.screenshot({ path: path.join(output, 'indicator.png') });
  await page.locator('#bluetooth-sync-status').click();
  await expect(page.locator('#settings-title')).toHaveText('再生・同期');
  await expect(page.locator('#settings-sync-status')).toContainText(device.name);
  await page.screenshot({ path: path.join(output, 'settings.png') });
  await page.locator('#settings-close').click();
  await page.locator('#btn-play').click();
  await expect.poll(() => page.evaluate(() => Math.abs(window.__presentationAudit.media.currentTime
    - Number(document.querySelector('#time-cur').dataset.seconds)))).toBeLessThan(.03);
  await expect.poll(() => page.evaluate(() => document.querySelector('#video-player').paused)).toBe(true);
  const endingDevice = await page.evaluate(() => window.practiceLabDesktop.getAudioOutput());
  assert.equal(endingDevice.transport, 'bluetooth');
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(output, 'summary.json'), JSON.stringify({ device, endingDevice, summary, errors }, null, 2));
  console.log(JSON.stringify({ ok: true, output, device, summary }, null, 2));
} finally { await app.close(); }
