const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const childProcess = require('node:child_process');
const { readUpdateConfiguration, validateUpdateConfiguration, writeUpdateConfiguration } = require('../../scripts/macos-update-config.cjs');
const { captureNormalInstall, automaticUpdatesAvailable } = require('../../scripts/macos-verification.cjs');
const valid = { provider: 'github', owner: 'Nattuhan', repo: 'practice-lab', updaterCacheDirName: 'practice-lab-updater' };

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'update-config-test-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const appPath = path.join(root, 'PracticeLab.app');
  fs.mkdirSync(path.join(appPath, 'Contents/Resources'), { recursive: true });
  fs.mkdirSync(path.join(appPath, 'Contents/Frameworks'), { recursive: true });
  return { root, appPath, file: path.join(appPath, 'Contents/Resources/app-update.yml') };
}

test('署名済みでも更新設定が欠落・不正なら自動更新可能と報告しない', t => {
  const { appPath, file, root } = fixture(t);
  const settingsPath = path.join(root, 'settings.json');
  const execute = () => ({ status: 0, stderr: 'Authority=Developer ID Application: Test\n' });
  const snapshot = () => captureNormalInstall({ appPath, settingsPath, execute });
  assert.equal(automaticUpdatesAvailable(snapshot()), false);
  writeUpdateConfiguration(file, valid, valid.updaterCacheDirName);
  assert.equal(automaticUpdatesAvailable(snapshot()), true);
  fs.writeFileSync(file, 'provider: github\nowner: someone-else\n');
  assert.equal(automaticUpdatesAvailable(snapshot()), false);
  fs.writeFileSync(file, 'provider: [');
  assert.equal(automaticUpdatesAvailable(snapshot()), false);
});

test('公開先・キャッシュ・チャンネルの誤設定を拒否する', () => {
  for (const overrides of [ { provider: 'generic' }, { owner: 'someone-else' }, { repo: 'other' },
    { updaterCacheDirName: undefined }, { host: 'example.com' }, { channel: 'beta' } ]) {
    assert.throws(() => validateUpdateConfiguration({ ...valid, ...overrides }));
  }
});

test('更新設定の生成は公開フィールドだけをコピーする', t => {
  const { file } = fixture(t);
  writeUpdateConfiguration(file, { ...valid, token: 'must-not-be-packaged' }, valid.updaterCacheDirName);
  assert.deepEqual(readUpdateConfiguration(file), valid);
  assert.equal(fs.readFileSync(file, 'utf8').includes('must-not-be-packaged'), false);
});

test('DMG・ZIPターゲットのないディレクトリビルドでも署名前に更新設定を生成する', async t => {
  const { root, appPath, file } = fixture(t);
  const sign = t.mock.method(childProcess, 'spawnSync', (command, args) => {
    if (args.at(-1) === appPath) assert.deepEqual(readUpdateConfiguration(file), valid);
    return { status: 0 };
  });
  delete require.cache[require.resolve('../../scripts/after-pack.cjs')];
  const afterPack = require('../../scripts/after-pack.cjs');
  await afterPack({ electronPlatformName: 'darwin', appOutDir: root, targets: [], packager: {
    config: { appId: 'jp.nattuhan.practicelab', publish: valid },
    appInfo: { productFilename: 'PracticeLab', updaterCacheDirName: valid.updaterCacheDirName },
  } });
  assert.deepEqual(readUpdateConfiguration(file), valid);
  assert.ok(sign.mock.calls.length > 0);
});
