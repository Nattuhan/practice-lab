import assert from "node:assert/strict";
import test from "node:test";

import { filterLibraryItems, sortLibraryItems } from "../src/library.js";
import { mutateSectionDraft } from "../src/section-editor.js";
import { formatBytes } from "../src/storage.js";

const sessions = [
  { id: "a", title: "Beta", tags: ["ライブ"], date: "2026-01-01", lastPracticedAt: null },
  { id: "b", title: "Alpha", tags: [], date: "2026-02-01", lastPracticedAt: "2026-03-01T00:00:00Z" },
];

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

test("容量を読みやすい単位へ変換する", () => {
  assert.equal(formatBytes(1024), "1.00 KB");
  assert.equal(formatBytes(10 * 1024 * 1024), "10.0 MB");
});
