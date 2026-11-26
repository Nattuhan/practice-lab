const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync, spawn } = require('node:child_process');
const { setTimeout: delay } = require('node:timers/promises');
const { wait, locations } = require('../../scripts/release_tasks.cjs');
const script = path.resolve(__dirname, '../../scripts/release_tasks.cjs');

function fixture(t, steps) {
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'release-tasks-'));
  t.after(() => fs.rmSync(cwd, { recursive: true, force: true }));
  const git = args => {
    const result = spawnSync('git', args, { cwd, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr); return result.stdout.trim();
  };
  git(['init', '-q']); git(['-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '--allow-empty', '-qm', 'source']);
  const file = path.join(cwd, 'plan.json');
  fs.writeFileSync(file, JSON.stringify({ sourceSha: git(['rev-parse', 'HEAD']), steps }));
  return { cwd, file, git, run: flags => spawnSync(process.execPath, [script, 'run', file, ...(flags || [])], { cwd, encoding: 'utf8' }) };
}
const command = code => [process.execPath, '-e', code];

test('失敗で後続を止め、明示再開では成功済みの外部操作を繰り返さない', t => {
  const f = fixture(t, [
    { id: 'submit', command: command("require('fs').appendFileSync('submissions', 'once\\n')") },
    { id: 'check', command: command("if (!require('fs').existsSync('allow')) process.exit(2)") },
    { id: 'publish', command: command("require('fs').writeFileSync('published', 'yes')") },
  ]);
  assert.equal(f.run().status, 1);
  assert.equal(fs.existsSync(path.join(f.cwd, 'published')), false);
  assert.equal(f.run().status, 1);
  fs.writeFileSync(path.join(f.cwd, 'allow'), 'yes');
  assert.equal(f.run(['--retry-failed']).status, 0);
  assert.equal(f.run().status, 0);
  assert.equal(fs.readFileSync(path.join(f.cwd, 'submissions'), 'utf8'), 'once\n');
  assert.equal(fs.readFileSync(path.join(f.cwd, 'published'), 'utf8'), 'yes');
});

test('再開時に計画や配布元コミットが変わっていたら実行しない', t => {
  const f = fixture(t, [{ id: 'submit', command: command("require('fs').appendFileSync('submissions', 'x')") }]);
  assert.equal(f.run().status, 0);
  f.git(['-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '--allow-empty', '-qm', 'changed']);
  assert.equal(f.run().status, 1);
  const plan = JSON.parse(fs.readFileSync(f.file)); plan.sourceSha = f.git(['rev-parse', 'HEAD']);
  fs.writeFileSync(f.file, JSON.stringify(plan));
  assert.equal(f.run().status, 1);
  assert.equal(fs.readFileSync(path.join(f.cwd, 'submissions'), 'utf8'), 'x');
});

test('二重起動を拒否し、待機は途中ログを返さず完了を一度だけ返す', { timeout: 20000 }, async t => {
  // Hold the worker until the duplicate has been checked. A fixed sleep can
  // expire while the second Node process starts on a busy runner.
  const f = fixture(t, [{ id: 'slow', command: command(`
    const fs = require('node:fs');
    fs.writeFileSync('started', '');
    const deadline = Date.now() + 12000;
    const timer = setInterval(() => {
      if (fs.existsSync('finish')) {
        clearInterval(timer);
        console.log('finished');
      } else if (Date.now() >= deadline) {
        process.exit(2);
      }
    }, 50);
  `) }]);
  const worker = spawn(process.execPath, [script, 'run', f.file], { cwd: f.cwd, stdio: 'ignore' });
  const exited = new Promise(resolve => worker.once('exit', resolve));
  const result = wait(f.file, 15);
  try {
    const started = path.join(f.cwd, 'started');
    const deadline = Date.now() + 8000;
    while (!fs.existsSync(started) && worker.exitCode === null && Date.now() < deadline) await delay(50);
    assert.equal(fs.existsSync(started), true, 'First worker did not start its command');
    const duplicate = f.run();
    assert.equal(duplicate.status, 1);
    assert.match(duplicate.stderr, /running worker/);
  } finally {
    fs.writeFileSync(path.join(f.cwd, 'finish'), '');
    await exited;
  }
  assert.equal((await result).status, 'succeeded');
  assert.equal(await exited, 0);
  assert.match(fs.readFileSync(path.join(`${f.file}.logs`, 'slow.log'), 'utf8'), /finished/);
});

test('中断した提出を失敗扱いに変えて安易に再実行しない', t => {
  const f = fixture(t, [{ id: 'submit', command: command("require('fs').writeFileSync('resubmitted', 'bad')") }]);
  const { loadPlan } = require('../../scripts/release_tasks.cjs');
  fs.writeFileSync(locations(f.file).state, JSON.stringify({ hash: loadPlan(f.file).hash,
    cwd: fs.realpathSync(f.cwd), status: 'running', completed: [], childPid: 2147483647 }));
  assert.equal(f.run(['--retry-failed']).status, 1);
  assert.equal(JSON.parse(fs.readFileSync(locations(f.file).state)).status, 'running');
  assert.equal(fs.existsSync(path.join(f.cwd, 'resubmitted')), false);
});

test('バックグラウンド再開後のwaitは前回の失敗を返さず今回の完了を待つ', async t => {
  const f = fixture(t, [{ id: 'verify', command: command("if (!require('fs').existsSync('allow')) process.exit(1); setTimeout(() => {}, 200)") }]);
  assert.equal(f.run().status, 1);
  fs.writeFileSync(path.join(f.cwd, 'allow'), 'yes');
  const result = spawnSync(process.execPath, [script, 'start', f.file, '--retry-failed'], { cwd: f.cwd, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.equal((await wait(f.file, 10)).status, 'succeeded');
});

test('配布元に未コミットの変更があれば後続を実行しない', t => {
  const f = fixture(t, [{ id: 'submit', command: command("require('fs').writeFileSync('submitted', 'bad')") }]);
  fs.writeFileSync(path.join(f.cwd, 'tracked'), 'old'); f.git(['add', 'tracked']);
  f.git(['-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-qm', 'tracked']);
  const plan = JSON.parse(fs.readFileSync(f.file)); plan.sourceSha = f.git(['rev-parse', 'HEAD']);
  fs.writeFileSync(f.file, JSON.stringify(plan)); fs.writeFileSync(path.join(f.cwd, 'tracked'), 'changed');
  assert.equal(f.run().status, 1);
  assert.equal(fs.existsSync(path.join(f.cwd, 'submitted')), false);
});
