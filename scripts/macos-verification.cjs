// Keep the ordinary signed installation and its settings outside local tests.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn, spawnSync } = require('node:child_process');
const { hasDeveloperIdSignature } = require('../desktop/update-policy.cjs');

const normalApp = '/Applications/PracticeLab.app';
const normalSettings = path.join(os.homedir(), 'Library/Application Support/practice-lab/settings.json');
const digest = file => fs.existsSync(file) ? crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') : null;

function captureNormalInstall({ appPath = normalApp, settingsPath = normalSettings, execute = spawnSync } = {}) {
  const exists = fs.existsSync(appPath);
  const signature = exists ? execute('/usr/bin/codesign', ['-dvv', appPath], { encoding: 'utf8', timeout: 10000 }) : { status: 1 };
  const verification = exists ? execute('/usr/bin/codesign', ['--verify', '--deep', '--strict', appPath], { encoding: 'utf8', timeout: 30000 }) : { status: 1 };
  const settings = fs.existsSync(settingsPath) ? JSON.parse(fs.readFileSync(settingsPath, 'utf8')) : {};
  return {
    appPath, settingsPath, exists,
    developerIdSigned: hasDeveloperIdSignature(signature),
    signatureValid: verification.status === 0,
    autoUpdate: settings.autoUpdate !== false,
    settingsDigest: digest(settingsPath),
    files: Object.fromEntries(['Contents/Info.plist', 'Contents/_CodeSignature/CodeResources',
      'Contents/Resources/app.asar', 'Contents/Resources/app-update.yml'].map(file => [file, digest(path.join(appPath, file))])),
  };
}
function assertNormalInstallPreserved(before, after) {
  if (JSON.stringify(before) !== JSON.stringify(after)) {
    throw new Error('検証中に普段使い版または設定が変わりました。自動で上書きや復元をせず、差分を確認してください。');
  }
}
function automaticUpdatesAvailable(state) {
  return state.exists && state.developerIdSigned && state.signatureValid && state.autoUpdate;
}
function validateVerificationApp(appPath, protectedApp = normalApp) {
  const resolved = fs.realpathSync(appPath);
  // Resolve aliases/symlinks as well: an alternate filename must not silently
  // turn a verification launch into a normal-profile launch.
  const protectedPath = fs.existsSync(protectedApp) ? fs.realpathSync(protectedApp) : path.resolve(protectedApp);
  if (resolved === protectedPath || resolved.startsWith(protectedPath + path.sep)) {
    throw new Error('普段使い版は検証対象に指定できません。desktop/dist配下のビルドを指定してください。');
  }
  const executable = path.join(resolved, 'Contents/MacOS/PracticeLab');
  if (!resolved.endsWith('.app') || !fs.existsSync(executable)) throw new Error('PracticeLabの.appを指定してください。');
  return executable;
}
function createVerificationProfile(parent = os.tmpdir()) {
  const profile = fs.mkdtempSync(path.join(parent, 'practice-lab-verification-'));
  fs.chmodSync(profile, 0o700);
  // Update checks and cloud connections belong to the ordinary installation.
  fs.writeFileSync(path.join(profile, 'settings.json'), JSON.stringify({ autoUpdate: false, cloud: { enabled: false } }), { mode: 0o600 });
  return profile;
}
async function main() {
  if (process.platform !== 'darwin') throw new Error('この補助スクリプトはMac用です。');
  const [argument, appPath] = process.argv.slice(2);
  const before = captureNormalInstall();
  console.log(JSON.stringify({ normalApp: before.appPath, developerIdSigned: before.developerIdSigned,
    signatureValid: before.signatureValid, startupUpdateCheck: before.autoUpdate,
    automaticUpdatesAvailable: automaticUpdatesAvailable(before) }, null, 2));
  if (argument === '--check') { process.exitCode = automaticUpdatesAvailable(before) ? 0 : 2; return; }
  if (argument !== '--launch' || !appPath) throw new Error('Usage: node scripts/macos-verification.cjs --check | --launch /path/to/PracticeLab.app');
  const executable = validateVerificationApp(appPath);
  const profile = createVerificationProfile();
  console.log(`検証用データ: ${profile}\n検証を終えたら、この検証用アプリを終了してください。`);
  const child = spawn(executable, [`--user-data-dir=${profile}`], { stdio: 'inherit' });
  const stop = () => child.kill('SIGTERM');
  process.once('SIGINT', stop); process.once('SIGTERM', stop);
  try {
    const code = await new Promise((resolve, reject) => {
      child.once('error', reject); child.once('exit', code => resolve(code));
    });
    if (code) process.exitCode = code;
  } finally {
    process.removeListener('SIGINT', stop); process.removeListener('SIGTERM', stop);
    assertNormalInstallPreserved(before, captureNormalInstall());
    console.log('普段使い版と設定が変更されていないことを確認しました。');
  }
}
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1; });
module.exports = { captureNormalInstall, assertNormalInstallPreserved, automaticUpdatesAvailable, validateVerificationApp, createVerificationProfile };
