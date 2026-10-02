import assert from 'node:assert/strict';
import test from 'node:test';
import { acceptsPlaybackShortcuts } from '../src/playback-shortcuts.js';

const element = (tagName, parentElement = null, extra = {}) => ({ tagName, parentElement, ...extra });

test('テンポ選択・入力欄・音量スライダー・ボタンのキーを再生に使わない', () => {
  for (const tag of ['SELECT', 'INPUT', 'TEXTAREA', 'BUTTON', 'A', 'AUDIO', 'VIDEO']) {
    const control = element(tag);
    assert.equal(acceptsPlaybackShortcuts(control), false, tag);
    assert.equal(acceptsPlaybackShortcuts(element('SPAN', control)), false, `${tag}の子要素`);
  }
});

test('編集可能な内容とアクセシブルな入力欄のキーを奪わない', () => {
  const editable = element('DIV', null, { isContentEditable: true });
  assert.equal(acceptsPlaybackShortcuts(element('SPAN', editable)), false);
  const textbox = element('DIV', null, { getAttribute: name => name === 'role' ? 'textbox' : null });
  assert.equal(acceptsPlaybackShortcuts(textbox), false);
});

test('ダイアログ内の空白でも背後のプレイヤーを操作しない', () => {
  const background = element('DIV', element('BODY'));
  assert.equal(acceptsPlaybackShortcuts(background, { dialogOpen: true }), false);
  assert.equal(acceptsPlaybackShortcuts(background, { dialogOpen: false }), true);
});

test('通常の曲画面と波形では再生ショートカットを維持する', () => {
  const body = element('BODY');
  assert.equal(acceptsPlaybackShortcuts(body), true);
  assert.equal(acceptsPlaybackShortcuts(element('DIV', body)), true);
});
