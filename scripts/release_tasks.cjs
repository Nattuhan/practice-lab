#!/usr/bin/env node
// Long builds, transfers and gh run watch belong to a process, not an LLM polling loop.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn, execFileSync } = require('node:child_process');

const alive = pid => {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try { process.kill(pid, 0); return true; } catch (error) { return error.code !== 'ESRCH'; }
};
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
function locations(file) {
  const plan = path.resolve(file);
  return { plan, state: `${plan}.state.json`, lock: `${plan}.lock`, logs: `${plan}.logs` };
}
function loadPlan(file) {
  const files = locations(file), raw = fs.readFileSync(files.plan), plan = JSON.parse(raw);
  if (!/^[a-f0-9]{40}$/.test(plan.sourceSha || '') || !Array.isArray(plan.steps) || !plan.steps.length) {
    throw new Error('Plan requires sourceSha and a nonempty steps array');
  }
  const ids = new Set();
  for (const step of plan.steps) {
    if (!/^[a-z0-9-]+$/.test(step.id || '') || ids.has(step.id) ||
        !Array.isArray(step.command) || !step.command.length ||
        step.command.some(arg => typeof arg !== 'string') || !step.command[0]) {
      throw new Error('Each step requires a unique id and a command argument array');
    }
    ids.add(step.id);
  }
  return { files, plan, hash: crypto.createHash('sha256').update(raw).digest('hex') };
}
function save(file, state) {
  // Rename makes status readers see either complete snapshot, never half JSON.
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(state, null, 2) + '\n', { mode: 0o600 });
  fs.renameSync(tmp, file);
}
function summary(state) {
  return { status: state.status, step: state.step, completed: state.completed,
    error: state.error, log: state.log };
}
async function run(file, { retryFailed = false, retryInterrupted = false } = {}) {
  const { files, plan, hash } = loadPlan(file);
  const cwd = fs.realpathSync(process.cwd());
  if (fs.existsSync(files.lock)) {
    if (alive(read(files.lock).pid)) throw new Error('This plan already has a running worker');
    fs.unlinkSync(files.lock);
  }
  const lock = fs.openSync(files.lock, 'wx', 0o600);
  fs.writeFileSync(lock, JSON.stringify({ pid: process.pid })); fs.closeSync(lock);
  let state, executing = false;
  try {
    state = fs.existsSync(files.state) ? read(files.state) :
      { hash, cwd, sourceSha: plan.sourceSha, completed: [], status: 'new' };
    if (state.hash !== hash || state.cwd !== cwd) throw new Error('Plan or working directory changed; use a new plan');
    if (state.status === 'failed' && !retryFailed) throw new Error('Inspect the failed log, then use --retry-failed');
    if (state.status === 'running') {
      if (alive(state.childPid)) throw new Error('The previous command is still running; do not submit it twice');
      // A crash may have happened after a remote mutation. Never replay silently.
      if (!retryInterrupted) throw new Error('Inspect remote state, then use --retry-interrupted');
    }
    fs.mkdirSync(files.logs, { recursive: true, mode: 0o700 });
    for (const step of plan.steps) {
      const head = execFileSync('git', ['rev-parse', 'HEAD'], { cwd, encoding: 'utf8' }).trim();
      if (head !== plan.sourceSha) throw new Error('HEAD changed from the approved sourceSha');
      execFileSync('git', ['diff', '--quiet', 'HEAD'], { cwd, stdio: 'pipe' });
      if (state.completed.includes(step.id)) continue;
      state = { ...state, status: 'running', step: step.id, error: undefined, childPid: undefined,
        workerPid: process.pid, log: path.join(files.logs, `${step.id}.log`) };
      executing = true; save(files.state, state);
      console.log(JSON.stringify({ event: 'started', ...summary(state) }));
      const fd = fs.openSync(state.log, 'a', 0o600);
      fs.writeSync(fd, `\n--- ${new Date().toISOString()} ---\n`);
      try {
        const child = spawn(step.command[0], step.command.slice(1), { cwd, stdio: ['ignore', fd, fd] });
        state.childPid = child.pid; save(files.state, state);
        await new Promise((resolve, reject) => {
          child.once('error', reject);
          child.once('exit', (code, signal) => code === 0 ? resolve() :
            reject(new Error(`${step.id} exited ${code ?? signal}`)));
        });
      } finally { fs.closeSync(fd); }
      state.completed.push(step.id); state.childPid = undefined;
      state.status = 'ready'; save(files.state, state);
      executing = false;
      console.log(JSON.stringify({ event: 'completed', step: step.id }));
    }
    state.status = 'succeeded'; save(files.state, state);
    console.log(JSON.stringify(summary(state)));
    return state;
  } catch (error) {
    if ((executing || ['new', 'ready'].includes(state?.status)) && state.hash === hash && state.cwd === cwd) {
      state.status = 'failed'; state.error = error.message; save(files.state, state);
    }
    throw error;
  } finally { fs.unlinkSync(files.lock); }
}
function wait(file, timeoutSeconds = 0) {
  const { files, hash } = loadPlan(file);
  return new Promise((resolve, reject) => {
    let timer;
    // Check the local snapshot and lock together. Directory notifications can
    // miss a rename or lock removal, particularly on Windows.
    const interval = setInterval(check, 250);
    function finish(error, state) {
      clearInterval(interval); clearTimeout(timer);
      if (error) reject(error); else resolve(summary(state));
    }
    function check() {
      if (!fs.existsSync(files.state)) return;
      try {
        const state = read(files.state);
        if (state.hash !== hash) return finish(new Error('Plan changed'));
        if (['failed', 'succeeded'].includes(state.status) && !fs.existsSync(files.lock)) finish(null, state);
      } catch (error) { finish(error); }
    }
    if (timeoutSeconds) timer = setTimeout(() => {
      const state = fs.existsSync(files.state) ? read(files.state) : { status: 'starting' };
      finish(null, state);
    }, timeoutSeconds * 1000);
    check();
  });
}
async function main() {
  const [mode, file, ...flags] = process.argv.slice(2);
  if (!file || !['run', 'start', 'status', 'wait'].includes(mode)) {
    throw new Error('Usage: release_tasks.cjs run|start|status|wait PLAN [--retry-failed|--retry-interrupted|--timeout-seconds=N]');
  }
  const timeoutFlag = flags.find(arg => arg.startsWith('--timeout-seconds='));
  if (flags.some(arg => !['--retry-failed', '--retry-interrupted'].includes(arg) && arg !== timeoutFlag)) throw new Error('Unknown option');
  const timeout = timeoutFlag ? Number(timeoutFlag.split('=')[1]) : 0;
  if (!Number.isFinite(timeout) || timeout < 0) throw new Error('Invalid timeout');
  if (mode === 'start') {
    const { files } = loadPlan(file);
    const fd = fs.openSync(`${files.plan}.worker.log`, 'a', 0o600);
    const child = spawn(process.execPath, [__filename, 'run', files.plan, ...flags],
      { detached: true, stdio: ['ignore', fd, fd] });
    fs.closeSync(fd);
    // Return only after this worker owns the snapshot. Otherwise wait could
    // mistake the previous failed attempt for the newly started attempt.
    await new Promise((resolve, reject) => {
      const interval = setInterval(check, 250);
      const timer = setTimeout(() => finish(new Error('Worker startup timed out; inspect the worker log')), 30000);
      function finish(error) {
        clearInterval(interval); clearTimeout(timer); child.removeListener('exit', exited);
        if (error) reject(error); else resolve();
      }
      function check() {
        if (fs.existsSync(files.state) && read(files.state).workerPid === child.pid) finish();
      }
      function exited(code) { finish(code ? new Error(`Worker exited ${code}; inspect ${files.plan}.worker.log`) : undefined); }
      child.once('error', finish); child.once('exit', exited); check();
    });
    child.unref();
    console.log(JSON.stringify({ pid: child.pid, state: files.state, log: `${files.plan}.worker.log` }));
  } else if (mode === 'run') {
    await run(file, { retryFailed: flags.includes('--retry-failed'), retryInterrupted: flags.includes('--retry-interrupted') });
  } else {
    const { files, hash } = loadPlan(file);
    if (mode === 'status' && read(files.state).hash !== hash) throw new Error('Plan changed');
    const state = mode === 'wait' ? await wait(file, timeout) : summary(read(files.state));
    console.log(JSON.stringify(state));
    if (state.status === 'failed') process.exitCode = 1;
  }
}
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1; });
module.exports = { run, wait, loadPlan, locations };
