import assert from "node:assert/strict";
import test from "node:test";

import { filterLibraryItems, sortLibraryItems } from "../src/library.js";
import { clampCustomLoopRange, moveCustomLoopRange, shouldRestartLoop } from "../src/loop-playback.js";
import { mutateSectionDraft, normalizeSectionDraft } from "../src/section-editor.js";
import { formatBytes } from "../src/storage.js";
import { extractWaveformPeaks } from "../src/waveform-peaks.js";

const sessions = [
  { id: "a", title: "Beta", tags: ["ライブ"], date: "2026-01-01", lastPracticedAt: null },
  { id: "b", title: "Alpha", tags: [], date: "2026-02-01", lastPracticedAt: "2026-03-01T00:00:00Z" },
];

test("ループ開始直後のメディア時刻の丸め誤差を再シークしない", () => {
  const range = { start: 29.042, end: 38.723 };
  assert.equal(shouldRestartLoop(29.0, range), false);
  assert.equal(shouldRestartLoop(28.8, range), true);
  assert.equal(shouldRestartLoop(38.723, range), true);
});

test("ドラッグ範囲を曲内に収め、誤クリック相当の短い範囲を無視する", () => {
  assert.deepEqual(clampCustomLoopRange(-2, 12, 10), { start: 0, end: 10, kind: "custom" });
  assert.equal(clampCustomLoopRange(3, 3.05, 10), null);
});

test("ドラッグ範囲の長さを保ったまま曲端で止める", () => {
  const range = { start: 3, end: 5 };
  assert.deepEqual(moveCustomLoopRange(range, 10, 8), { start: 6, end: 8, kind: "custom" });
  assert.deepEqual(moveCustomLoopRange(range, -10, 8), { start: 0, end: 2, kind: "custom" });
});

test("ライブラリを曲名・タグ・未練習で絞り込める", () => {
  assert.deepEqual(filterLibraryItems(sessions, { query: "ライブ" }).map(item => item.id), ["a"]);
  assert.deepEqual(filterLibraryItems(sessions, { filter: "unpracticed" }).map(item => item.id), ["a"]);
});

test("ライブラリを最近練習した順と曲名順に並べられる", () => {
  assert.deepEqual(sortLibraryItems(sessions, "recent").map(item => item.id), ["b", "a"]);
  assert.deepEqual(sortLibraryItems(sessions, "title").map(item => item.id), ["b", "a"]);
});

test("セクションを連続した小節範囲のまま分割・結合できる", () => {
  const split = mutateSectionDraft([{ label: "verse", startBar: 1, endBar: 4 }], 0, "split");
  assert.deepEqual(split.map(item => [item.startBar, item.endBar]), [[1, 2], [3, 4]]);
  const merged = mutateSectionDraft(split, 0, "merge");
  assert.deepEqual(merged.map(item => [item.startBar, item.endBar]), [[1, 4]]);
});

test("自動解析の重複と末尾の空白を連続した小節範囲へ補正する", () => {
  const normalized = normalizeSectionDraft([
    { label: "start", startBar: 1, endBar: 2 },
    { label: "verse", startBar: 1, endBar: 8 },
    { label: "chorus", startBar: 9, endBar: 11 },
  ], 12);

  assert.deepEqual(normalized.map(section => [section.startBar, section.endBar]), [[1, 2], [3, 8], [9, 12]]);
});

test("容量を読みやすい単位へ変換する", () => {
  assert.equal(formatBytes(1024), "1.00 KB");
  assert.equal(formatBytes(10 * 1024 * 1024), "10.0 MB");
});

test("実音源のサンプルから表示用波形を生成する", () => {
  const channel = Float32Array.from([0, .1, -.2, .4, -.8, .2, -.1, 0]);
  const peaks = extractWaveformPeaks({
    numberOfChannels: 1,
    length: channel.length,
    getChannelData: () => channel,
  }, 4);
  assert.equal(peaks.length, 4);
  assert.ok(peaks[2] > peaks[0]);
  assert.equal(Math.max(...peaks), 1);
});
