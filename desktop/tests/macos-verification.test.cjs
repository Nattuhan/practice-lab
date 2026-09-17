const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { captureNormalInstall, assertNormalInstallPreserved, automaticUpdatesAvailable, validateVerificationApp, createVerificationProfile } = require('../../scripts/macos-verification.cjs');

test('検証プロファイルは通常設定と分離し、更新とクラウド接続を無効にする', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'verification-test-'));
  try {
    const profile = createVerificationProfile(root);
    assert.notEqual(profile, root);
    assert.deepEqual(JSON.parse(fs.readFileSync(path.join(profile, 'settings.json'))), { autoUpdate: false, cloud: { enabled: false } });
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('通常アプリの入れ替えや自動更新設定の変更を検出し、勝手に復元しない', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'verification-test-'));
  const appPath = path.join(root, 'PracticeLab.app'), settingsPath = path.join(root, 'settings.json');
  fs.mkdirSync(path.join(appPath, 'Contents/Resources'), { recursive: true });
  const asar = path.join(appPath, 'Contents/Resources/app.asar'); fs.writeFileSync(asar, 'signed build');
  fs.writeFileSync(settingsPath, '{"autoUpdate":true}');
  const execute = () => ({ status: 0, stderr: 'Authority=Developer ID Application: Test\n' });
  const snapshot = () => captureNormalInstall({ appPath, settingsPath, execute });
  try {
    const before = snapshot(); assert.ok(automaticUpdatesAvailable(before));
    assertNormalInstallPreserved(before, snapshot());
    fs.writeFileSync(asar, 'local build');
    assert.throws(() => assertNormalInstallPreserved(before, snapshot()), /普段使い版/);
    assert.equal(fs.readFileSync(asar, 'utf8'), 'local build');
    fs.writeFileSync(asar, 'signed build'); fs.writeFileSync(settingsPath, '{"autoUpdate":false}');
    assert.throws(() => assertNormalInstallPreserved(before, snapshot()), /設定/);
    assert.equal(automaticUpdatesAvailable(snapshot()), false);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('普段使いアプリを検証起動へ渡す操作を拒否する', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'verification-test-'));
  const app = path.join(root, 'PracticeLab.app');
  fs.mkdirSync(path.join(app, 'Contents/MacOS'), { recursive: true });
  fs.writeFileSync(path.join(app, 'Contents/MacOS/PracticeLab'), 'test');
  try { assert.throws(() => validateVerificationApp(app, app), /普段使い版/); }
  finally { fs.rmSync(root, { recursive: true, force: true }); }
});
