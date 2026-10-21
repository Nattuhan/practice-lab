const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync, spawn } = require('node:child_process');
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

test('二重起動を拒否し、待機は途中ログを返さず完了を一度だけ返す', async t => {
  const f = fixture(t, [{ id: 'slow', command: command("setTimeout(() => console.log('finished'), 500)") }]);
  const worker = spawn(process.execPath, [script, 'run', f.file], { cwd: f.cwd, stdio: 'ignore' });
  const exited = new Promise(resolve => worker.once('exit', resolve));
  const result = wait(f.file);
  // State creation is an event, not repeated remote status queries.
  await new Promise(resolve => {
    const watcher = fs.watch(f.cwd, () => {
      if (fs.existsSync(locations(f.file).state)) { watcher.close(); resolve(); }
    });
    if (fs.existsSync(locations(f.file).state)) { watcher.close(); resolve(); }
  });
  const duplicate = f.run();
  assert.equal(duplicate.status, 1);
  assert.match(duplicate.stderr, /running worker/);
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
  assert.equal((await wait(f.file)).status, 'succeeded');
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
