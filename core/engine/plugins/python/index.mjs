// W.Alter engine — persistent Python kernel (convergence with Unharnessed, 2026-11-16; docs/07-CONVERGENCE.md § 2).
//
// Registers the model-facing tool `python`: one persistent Python kernel per agent session (a conversation, a
// sub-agent), started on first use in its own bubble — a transient systemd unit running as the unprivileged
// `walter-sandbox` user: whole filesystem read-only, its workspace the only writable place, no secret readable, no
// local service or private network reachable (public internet allowed), memory/CPU/task ceilings. Model-generated
// code never runs with the engine's root rights.
//
// From Python every engine tool is reachable (`await tools.<name>(...)`): each call goes through this registry's
// `execute` — Walter's policy (guard + pre-execute), approvals, post-policy, logs — exactly like a direct call, and
// is recorded on the session as `tool/ptc-dispatch` (the kernel's own run_code vocabulary). Exclusive tools run one
// at a time, concurrency-safe ones (fs reads, sub-agents) in parallel. Background work (`bash(..., background=True)`,
// `spawn(...)`) becomes an engine job owned by the session: the kernel's own job registry wakes an idle agent when
// it settles. The namespace is snapshotted after each cell; a kernel that comes back (engine restart, crash, idle
// stop, interrupt that had to kill it) restores it. Jobs do not survive a kernel restart (they are reported failed).
//
// Config (rendered by `walter harness install dsh` from [dsh.engine] python = "on"):
//   stateDir (one folder per session: workspace + .snapshot), python, runtimeDir, user, memoryMax, tasksMax,
//   cpuQuota, cellTimeoutMs, idleMs, maxOutputChars, sandbox ("systemd" | "none": tests only, never composed).
import { spawn, execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { appendFileSync, chownSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

export const name = 'walter-python';
export const inject = ['tools'];
export const TOOL_NAME = 'python';
const run = promisify(execFile);

let hostRequire = createRequire(import.meta.url);
try { hostRequire.resolve('@deepseek-ai/dsh-tools'); }
catch { hostRequire = createRequire(process.env.WALTER_DSH_PACKAGE || '/opt/dsh/package.json'); }

const HERE = dirname(fileURLToPath(import.meta.url));
export const DEFAULTS = {
  python: '/services/python/engine-python/bin/python', runtimeDir: join(HERE, 'runtime'), user: 'walter-sandbox',
  memoryMax: '4G', tasksMax: 256, cpuQuota: '200%', cellTimeoutMs: 600_000, idleMs: 20 * 60_000,
  interruptGraceMs: 5_000, maxOutputChars: 20_000, sandbox: 'systemd', startTimeoutMs: 30_000,
};
// Private ranges the kernel never reaches: the VM's own services (PostgreSQL, gateways, the engine API), Docker,
// the tailnet (the Mac), the cloud metadata endpoint. DNS goes to the local resolver only.
export const DENIED_NETWORKS = ['127.0.0.0/8', '::1/128', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16',
  '169.254.0.0/16', '100.64.0.0/10', 'fc00::/7', 'fe80::/10'];
const RESOLVER = '127.0.0.53/32';

export const DESCRIPTION = [
  'Run Python in your persistent kernel (one per conversation): variables, imports and functions persist across calls',
  'and survive context compaction. Top-level `await` works; the last expression\'s repr is returned, print() output',
  'is shown. Keep large intermediate data in variables instead of printing it.',
  'Engine tools from Python: `await tools.search("memory")` finds tools, `await tools.describe(name)` gives their',
  'parameters, `await tools.<name>(**args)` runs one under the same policy as a direct call; run independent calls',
  'together with `await asyncio.gather(...)`.',
  '`await bash("cmd")` → .stdout .stderr .code .ok; `bash("cmd", background=True)` or `spawn(coro, label)` start an',
  'engine job and return it at once (job.id for job_output / job_kill); end your turn, you are woken when it ends',
  '(`await job.wait()` only if you must block). `await delegate(prompt, poste="code")` runs a sub-agent in its own',
  'context (poste = a Walter Router task) and returns its result; `await delegate_all([...])` runs several at once.',
  'Sandbox: unprivileged, the current directory is your persistent workspace (the only writable place), no secrets,',
  'no local services (reach Walter only through `tools`), public internet allowed. Host administration: the bash tool.',
].join(' ');

const sha16 = (s) => createHash('sha256').update(String(s)).digest('hex').slice(0, 16);
const textOf = (content) => (content || []).filter((b) => b?.type === 'text').map((b) => b.text).join('\n');
const day = () => new Date().toISOString().slice(0, 10);

/** Keep the head and the tail of a long output (the middle is what the model needs least). */
export function clip(text, max) {
  if (text.length <= max) return text;
  const head = Math.floor(max * 0.4), tail = max - head;
  return `${text.slice(0, head)}\n… [${text.length - max} characters omitted] …\n${text.slice(-tail)}`;
}

/** Tools matching a query, best first: name hits weigh more than description hits. */
export function searchTools(schemas, query, limit = 8) {
  const words = String(query || '').toLowerCase().split(/[^\p{L}\p{N}_]+/u).filter((w) => w.length > 1);
  const scored = schemas.filter((s) => s.name !== TOOL_NAME).map((s) => {
    const nameL = s.name.toLowerCase(), desc = String(s.description || '').toLowerCase();
    const score = words.length ? words.reduce((n, w) => n + (nameL.includes(w) ? 3 : 0) + (desc.includes(w) ? 1 : 0), 0) : 1;
    return { score, name: s.name, description: String(s.description || '').slice(0, 240) };
  }).filter((s) => s.score > 0).sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
  return scored.slice(0, Math.max(1, Math.min(50, limit || 8))).map(({ name, description }) => ({ name, description }));
}

/** The systemd-run command line of a kernel's bubble. */
export function bubbleArgv(cfg, { unit, dir, uid, gid }) {
  const props = [
    `User=${uid}`, `Group=${gid}`, 'ProtectSystem=strict', 'ProtectHome=yes', 'PrivateTmp=yes', 'PrivateDevices=yes',
    'NoNewPrivileges=yes', 'CapabilityBoundingSet=', 'AmbientCapabilities=', 'RestrictSUIDSGID=yes',
    'ProtectKernelTunables=yes', 'ProtectKernelModules=yes', 'ProtectKernelLogs=yes', 'ProtectControlGroups=yes',
    'ProtectClock=yes', 'ProtectHostname=yes', 'RestrictNamespaces=yes', 'LockPersonality=yes', 'RestrictRealtime=yes',
    'UMask=0077', `BindPaths=${dir}:/kernel`, `IPAddressDeny=${DENIED_NETWORKS.join(' ')}`, `IPAddressAllow=${RESOLVER}`,
    `MemoryMax=${cfg.memoryMax}`, `TasksMax=${cfg.tasksMax}`, `CPUQuota=${cfg.cpuQuota}`, 'KillMode=control-group',
    'TimeoutStopSec=20',
  ];
  // the kernel's own interpreter first: `python`, `pip` in bash() are the kernel's (only python3 is on the host PATH)
  const env = { HOME: '/kernel', PATH: `${dirname(cfg.python)}:/usr/local/bin:/usr/bin:/bin`,
    PYTHONPATH: cfg.runtimeDir, PYTHONUNBUFFERED: '1',
    PYTHONUSERBASE: '/kernel/.local', MPLBACKEND: 'Agg', LANG: 'C.UTF-8',
    WALTER_KERNEL_SNAPSHOT: '/kernel/.snapshot/state.pkl', WALTER_KERNEL_BIND_JOBS: '1' };
  return ['systemd-run', '--wait', '--pipe', '--collect', '--quiet', `--unit=${unit}`, '--working-directory=/kernel',
    ...props.map((p) => `--property=${p}`), ...Object.entries(env).map(([k, v]) => `--setenv=${k}=${v}`),
    // -P: the workspace (cwd) is not put first on sys.path, so a file the model writes there cannot shadow a module
    cfg.python, '-P', '-c', 'import walter_kernel; walter_kernel.main()'];
}

class Kernel {
  constructor(plugin, key, agent) {
    this.plugin = plugin; this.cfg = plugin.cfg; this.key = key; this.agent = agent;
    this.dir = join(this.cfg.stateDir, key); this.unit = `walter-python-${key}`;
    this.child = null; this.waiters = new Map(); this.cells = new Map(); this.aborts = new Map(); this.jobs = new Map();
    this.ids = 0; this.dispatches = 0; this.lane = Promise.resolve(); this.exclusive = Promise.resolve();
    this.snapshotting = false; this.idleTimer = null; this.stderr = ''; this.restored = null; this.names = [];
    // background jobs still running, kept outside the bubble (root-owned): an engine restart stops them, and the next
    // cell of the conversation is told which ones (they are not silently lost)
    this.jobsFile = join(this.cfg.stateDir, `${key}.jobs.json`); this.keepJobs = false; this.lost = null;
  }

  saveJobs() {
    if (this.keepJobs) return;
    const running = [...this.jobs.values()].filter((j) => j.engine).map((j) => ({ engine: j.engine, label: j.label, started: j.started }));
    try { if (running.length) writeFileSync(this.jobsFile, JSON.stringify(running)); else rmSync(this.jobsFile, { force: true }); } catch { /* notice only */ }
  }

  log(event, extra = {}) {
    try { appendFileSync(join(this.cfg.stateDir, `kernels-${day()}.jsonl`), JSON.stringify({ at: new Date().toISOString(), key: this.key, event, ...extra }) + '\n'); } catch { /* observability only */ }
  }

  async start() {
    const t0 = performance.now();
    mkdirSync(join(this.dir, '.snapshot'), { recursive: true, mode: 0o700 });
    if (this.cfg.sandbox !== 'none') {
      const { uid, gid } = this.plugin.identity();
      for (const p of [this.dir, join(this.dir, '.snapshot')]) chownSync(p, uid, gid);
      // a unit left by a previous engine process: stopping it makes it flush its snapshot (SIGTERM) before we restore
      await run('systemctl', ['stop', `${this.unit}.service`], { timeout: 30_000 }).catch(() => {});
    }
    const restoreFrom = existsSync(join(this.dir, '.snapshot', 'state.pkl'));
    try {
      this.lost = JSON.parse(readFileSync(this.jobsFile, 'utf8'));
      rmSync(this.jobsFile, { force: true });
      if (this.lost?.length) this.log('jobs_lost', { jobs: this.lost.map((j) => j.engine) });
    } catch { this.lost = null; }
    const argv = this.cfg.sandbox === 'none'
      ? [this.cfg.python, '-P', '-c', 'import walter_kernel; walter_kernel.main()']
      : bubbleArgv(this.cfg, { unit: this.unit, dir: this.dir, ...this.plugin.identity() });
    const env = this.cfg.sandbox === 'none'
      ? { PATH: process.env.PATH, PYTHONPATH: this.cfg.runtimeDir, HOME: this.dir,
        WALTER_KERNEL_SNAPSHOT: join(this.dir, '.snapshot', 'state.pkl'), WALTER_KERNEL_BIND_JOBS: '1' }
      : { PATH: process.env.PATH };
    const child = spawn(argv[0], argv.slice(1), { cwd: this.cfg.sandbox === 'none' ? this.dir : '/', env, stdio: ['pipe', 'pipe', 'pipe'] });
    this.child = child;
    let buf = '';
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      buf += chunk;
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 1);
        if (!line.trim()) continue;
        let ev; try { ev = JSON.parse(line); } catch { continue; }
        this.onEvent(ev);
      }
    });
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (c) => { this.stderr = (this.stderr + c).slice(-4000); });
    child.stdin.on('error', () => {});
    const ready = new Promise((resolve, reject) => {
      this.waiters.set('ready', { resolve, reject });
      setTimeout(() => reject(new Error(`python kernel did not start in ${this.cfg.startTimeoutMs} ms`)), this.cfg.startTimeoutMs).unref?.();
    });
    child.on('exit', (code, sig) => this.onExit(code, sig));
    await ready;
    if (restoreFrom) {
      const r = await this.request({ type: 'restore' }).catch((e) => ({ status: 'error', error: { message: String(e) } }));
      this.restored = r.status === 'ok' ? r.restore : { failed: r.error };
      if (r.names) this.names = r.names;
    }
    this.log('start', { ms: Math.round(performance.now() - t0), restored: this.restored?.restored ?? 0,
      restore_failed: Object.keys(this.restored?.failed || {}).length, sandbox: this.cfg.sandbox });
    this.touch();
  }

  onExit(code, sig) {
    const why = new Error(`python kernel exited (${sig || code})${this.stderr ? `: ${this.stderr.slice(-300)}` : ''}`);
    this.child = null;
    for (const [, w] of this.waiters) w.reject(why);
    this.waiters.clear();
    for (const [, a] of this.aborts) a.abort(why);
    for (const [jid, job] of this.jobs) job.settle({ status: 'failed', detail: 'python kernel stopped; background work does not survive it' }), this.jobs.delete(jid);
    this.saveJobs();
    clearTimeout(this.idleTimer);
    this.plugin.kernels.delete(this.key);
    this.log('exit', { code, signal: sig });
  }

  send(obj) {
    if (!this.child) throw new Error('python kernel is not running');
    this.child.stdin.write(JSON.stringify(obj) + '\n');
  }

  request(req) {
    const id = req.id || `r${++this.ids}`;
    return new Promise((resolve, reject) => {
      this.waiters.set(id, { resolve, reject });
      try { this.send({ ...req, id }); } catch (e) { this.waiters.delete(id); reject(e); }
    });
  }

  onEvent(ev) {
    const w = (id) => { const x = this.waiters.get(id); this.waiters.delete(id); return x; };
    switch (ev.event) {
      case 'ready': w('ready')?.resolve(ev); break;
      case 'done': w(ev.id)?.resolve(ev); break;
      case 'bye': break;
      case 'out': {
        const cell = ev.id && this.cells.get(ev.id);
        if (cell) cell.out.push(ev.stream === 'stderr' ? ev.text : ev.text);
        else if (ev.job && this.jobs.has(ev.job)) this.jobs.get(ev.job).append(ev.text, ev.stream);
        break;
      }
      case 'result': { const cell = this.cells.get(ev.id); if (cell) cell.result = ev.text; break; }
      case 'host': void this.onHost(ev); break;
      case 'host_cancel': this.aborts.get(ev.id)?.abort(new Error('cancelled by the kernel')); break;
      case 'job': this.onJob(ev); break;
      default: break;
    }
  }

  async onHost(ev) {
    const cell = ev.cell ? this.cells.get(ev.cell) : null;
    const agent = cell?.exec.agent ?? this.agent;
    const ac = new AbortController();
    this.aborts.set(ev.id, ac);
    const signal = cell ? AbortSignal.any([cell.exec.signal, ac.signal]) : ac.signal;
    try {
      let result;
      const schemas = () => this.plugin.ctx.tools.schemas(agent);
      if (ev.method === 'search') result = searchTools(schemas(), ev.params?.query, ev.params?.limit);
      else if (ev.method === 'describe') {
        const s = schemas().find((x) => x.name === ev.params?.name);
        if (!s) throw new Error(`no tool named ${ev.params?.name}; await tools.search("…")`);
        result = { name: s.name, description: s.description, parameters: s.parameters };
      } else if (ev.method === 'tool') result = await this.callTool(ev, cell, agent, signal);
      else throw new Error(`unknown host method ${ev.method}`);
      this.send({ type: 'host_reply', id: ev.id, ok: true, result: result === undefined ? null : result });
    } catch (e) {
      try { this.send({ type: 'host_reply', id: ev.id, ok: false, error: String(e?.message || e).slice(0, 4000) }); } catch { /* kernel gone */ }
    } finally { this.aborts.delete(ev.id); }
  }

  async callTool(ev, cell, agent, signal) {
    const toolName = String(ev.params?.name || '');
    if (toolName === TOOL_NAME) throw new Error('python cannot call itself');
    const args = ev.params?.arguments && typeof ev.params.arguments === 'object' ? ev.params.arguments : {};
    const parentCallId = cell ? cell.exec.callId : `python:${this.key}:${ev.job || 'job'}`;
    const subCallId = `${parentCallId}:py:${++this.dispatches}`;
    const rootCallId = cell?.exec.rootCallId ?? parentCallId;
    const input = { callId: subCallId, rootCallId, name: toolName, arguments: args, ...(agent ? { agent } : {}),
      ...(cell?.exec.token ? { parent: cell.exec.token } : {}), signal };
    const tools = this.plugin.ctx.tools;
    let mode = 'exclusive';
    try { mode = tools.executionMode(input).kind; } catch { /* fail closed: exclusive */ }
    const go = async () => {
      try { agent?.session?.append?.('tool/ptc-dispatch-start', { rootCallId, parentCallId, subCallId, name: toolName, arguments: args }); } catch { /* log only */ }
      const result = await tools.execute(input);
      try { agent?.session?.append?.('tool/ptc-dispatch', { rootCallId, parentCallId, subCallId, name: toolName, arguments: args, isError: Boolean(result.isError), content: result.content }); } catch { /* log only */ }
      this.plugin.count(result.isError ? 'tool_error' : 'tool_ok');
      if (result.isError) throw new Error(result.error?.message || textOf(result.content) || `${toolName} failed`);
      return result.value !== undefined ? result.value : textOf(result.content);
    };
    if (mode === 'parallel') return go();
    const turn = this.exclusive.then(go, go);
    this.exclusive = turn.catch(() => {});
    return turn;
  }

  onJob(ev) {
    if (ev.state === 'start') {
      const jobs = this.plugin.jobs();
      let settle = () => {}, append = () => {};
      const done = new Promise((resolve) => { settle = resolve; });
      const entry = { settle: (o) => settle(o), append: (t, s) => append(t, s), label: ev.label };
      this.jobs.set(ev.job, entry);
      // the kernel waits for this answer: the model is shown the engine's id (job_output, job_kill, the wake-up notice)
      const bind = (engine, error = null) => { try { this.send({ type: 'job_bound', job: ev.job, engine, ...(error ? { error } : {}) }); } catch { /* kernel gone */ } };
      if (!jobs || !this.agent) return bind(null);
      try {
        const id = jobs.start({ kind: 'python', label: `python: ${ev.label}`.slice(0, 200), owner: this.agent.id ?? this.agent.session?.id,
          outputLimitBytes: 16_000,
          run: (handle) => {
            append = (t, s) => handle.append(t, { channel: s === 'stderr' ? 'stderr' : 'stdout' });
            return { cancel: () => { try { this.send({ type: 'job_kill', job: ev.job }); } catch { settle({ status: 'killed' }); } }, done };
          } });
        entry.engine = id; entry.started = new Date().toISOString();
        bind(id);
        this.saveJobs();
      } catch (e) {
        const error = String(e?.message || e).slice(0, 300);
        this.plugin.ctx.logger?.warn?.(`walter-python: job not registered (${error})`);
        bind(null, error);
      }
      return;
    }
    const entry = this.jobs.get(ev.job);
    if (!entry) return;
    this.jobs.delete(ev.job);
    this.saveJobs();
    entry.settle(ev.state === 'completed' ? { status: 'completed', ...(ev.result ? { result: ev.result } : {}) }
      : ev.state === 'killed' ? { status: 'killed' } : { status: 'failed', detail: String(ev.result || 'failed').slice(0, 500) });
    this.touch();
  }

  touch() {
    clearTimeout(this.idleTimer);
    this.idleTimer = setTimeout(() => {
      if (this.jobs.size || this.cells.size) return this.touch();
      this.log('idle_stop');
      void this.stop('idle');
    }, this.cfg.idleMs);
    this.idleTimer.unref?.();
  }

  /** One cell at a time per kernel; the next waits for the previous and for its snapshot. */
  queue(fn) {
    const next = this.lane.then(fn, fn);
    this.lane = next.catch(() => {});
    return next;
  }

  async cell(code, exec, timeoutMs) {
    const id = `c${++this.ids}`;
    const cell = { exec, out: [], result: null, timedOut: false };
    this.cells.set(id, cell);
    const names = (() => { try { return this.plugin.ctx.tools.schemas(exec.agent).map((s) => s.name).filter((n) => n !== TOOL_NAME); } catch { return []; } })();
    const t0 = performance.now();
    let killed = false;
    const interrupt = () => {
      try { this.send({ type: 'interrupt' }); } catch { return; }
      const grace = setTimeout(() => { if (this.cells.has(id)) { killed = true; void this.kill('interrupt not honoured'); } }, this.cfg.interruptGraceMs);
      grace.unref?.();
    };
    const onAbort = () => interrupt();
    exec.signal?.addEventListener?.('abort', onAbort, { once: true });
    const timer = setTimeout(() => { cell.timedOut = true; interrupt(); }, timeoutMs);
    timer.unref?.();
    let done;
    try {
      done = await this.request({ type: 'execute', id, code, tools: names });
    } catch (e) {
      done = { status: killed ? 'interrupted' : 'error', error: { type: 'KernelExited', message: `${String(e?.message || e).slice(0, 300)} — the next call restarts it from the last snapshot` } };
    } finally {
      clearTimeout(timer);
      exec.signal?.removeEventListener?.('abort', onAbort);
      this.cells.delete(id);
    }
    if (done.names) this.names = done.names;
    this.plugin.count(`cell_${done.status}`);
    this.log('cell', { ms: Math.round(performance.now() - t0), status: done.status, timed_out: cell.timedOut || undefined });
    if (this.child) void this.snapshot();
    this.touch();
    return this.render(cell, done);
  }

  render(cell, done) {
    const parts = [];
    const out = cell.out.join('');
    if (out) parts.push(out.replace(/\n$/, ''));
    if (cell.result !== null) parts.push(`→ ${cell.result}`);
    if (done.status === 'error') parts.push(`${done.error?.traceback || `${done.error?.type}: ${done.error?.message}`}`.replace(/\n$/, ''));
    if (done.status === 'interrupted') parts.push(cell.timedOut ? `[interrupted: the cell exceeded ${Math.round(this.cfg.cellTimeoutMs / 1000)} s — use background=True / spawn() for long work]` : `[interrupted]${done.error?.type === 'KernelExited' ? ` ${done.error.message}` : ''}`);
    if (done.jobs?.length) parts.push(`[background: ${done.jobs.map((j) => `${j.engine || j.job} ${j.label}`).join('; ')} — you will be woken when they end; job_output / job_kill take these ids]`);
    if (this.lost?.length) {
      parts.unshift(`[background jobs stopped by an engine restart: ${this.lost.map((j) => `${j.engine} ${j.label}`).join('; ')} — start them again if still needed]`);
      this.lost = null;
    }
    if (this.restored && !this.restored.reported) {
      this.restored.reported = true;
      const failed = Object.keys(this.restored.failed || {});
      parts.unshift(`[kernel restarted: ${this.restored.restored ?? 0} variables restored from the last snapshot${failed.length ? `, not restored: ${failed.slice(0, 10).join(', ')}` : ''}]`);
    }
    const text = parts.join('\n') || '(no output)';
    return clip(text, this.cfg.maxOutputChars);
  }

  async snapshot() {
    if (this.snapshotting || !this.child) return;
    this.snapshotting = true;
    const t0 = performance.now();
    try {
      const r = await this.queue(() => this.request({ type: 'snapshot' }));
      this.log('snapshot', { ms: Math.round(performance.now() - t0), status: r.status, saved: r.snapshot?.saved, bytes: r.snapshot?.bytes, skipped: Object.keys(r.snapshot?.skipped || {}).length });
    } catch { /* the kernel went away; the previous snapshot stays */ } finally { this.snapshotting = false; }
  }

  async stop(reason) {
    if (!this.child) return;
    // not the owner's intent (the engine unloads, the agent is disposed): running jobs are reported at the next start
    if (this.jobs.size && /unloading|disposed/.test(reason)) this.keepJobs = true;
    const child = this.child;
    const gone = new Promise((resolve) => child.once('exit', resolve));
    try { this.send({ type: 'shutdown', reason }); } catch { /* already closing */ }
    const t = setTimeout(() => void this.kill(`${reason}: no clean exit`), 20_000);
    await gone; clearTimeout(t);
  }

  async kill(reason) {
    this.log('kill', { reason });
    if (this.cfg.sandbox !== 'none') await run('systemctl', ['kill', '--signal=SIGKILL', `${this.unit}.service`], { timeout: 10_000 }).catch(() => {});
    try { this.child?.kill('SIGKILL'); } catch { /* gone */ }
  }
}

export function apply(ctx, config = {}) {
  const { defineTool } = hostRequire('@deepseek-ai/dsh-tools');
  const cfg = { ...DEFAULTS, ...config };
  if (!cfg.stateDir) throw new Error('walter-python: stateDir is required');
  mkdirSync(cfg.stateDir, { recursive: true, mode: 0o700 });
  const counters = new Map();
  let ident = null;
  const plugin = {
    ctx, cfg, kernels: new Map(), starting: new Map(),
    count: (k) => counters.set(k, (counters.get(k) || 0) + 1),
    jobs: () => { try { return ctx.get?.('jobs'); } catch { return undefined; } },
    identity: () => {
      if (ident) return ident;
      const out = (args) => String(hostRequire('node:child_process').execFileSync('id', args)).trim();
      ident = { uid: Number(out(['-u', cfg.user])), gid: Number(out(['-g', cfg.user])) };
      if (!ident.uid) throw new Error(`walter-python: sandbox user ${cfg.user} resolves to root`);
      return ident;
    },
  };
  if (cfg.sandbox !== 'none') plugin.identity();   // fail at load, not at the first call, when the user is missing

  const kernelFor = async (agent) => {
    const sid = agent?.id ?? agent?.session?.id;
    if (!sid) throw new Error('python requires an owning agent session');
    const key = sha16(sid);
    const live = plugin.kernels.get(key);
    if (live?.child) { live.agent = agent; return live; }
    if (plugin.starting.has(key)) return plugin.starting.get(key);
    const k = new Kernel(plugin, key, agent);
    const p = (async () => {
      try {
        try { writeFileSync(join(cfg.stateDir, `${key}.owner.json`), JSON.stringify({ session: String(sid), at: new Date().toISOString() })); } catch { /* ops hint only */ }
        await k.start();
        plugin.kernels.set(key, k);
        agent?.ctx?.effect?.(() => () => { void k.stop('agent disposed'); }, 'walter-python kernel');
        return k;
      } finally { plugin.starting.delete(key); }
    })();
    plugin.starting.set(key, p);
    return p;
  };

  ctx.on?.('workspace/session-stop', ({ sessionId }) => { const k = plugin.kernels.get(sha16(sessionId)); if (k) void k.stop('session archived'); });
  ctx.effect?.(() => async () => { await Promise.allSettled([...plugin.kernels.values()].map((k) => k.stop('engine unloading'))); }, 'walter-python kernels');

  ctx.tools.register(defineTool({
    name: TOOL_NAME,
    description: DESCRIPTION,
    parameters: {
      code: { type: 'string', required: true, description: 'Python code to run in the persistent kernel.' },
      description: { type: 'string', description: 'A short label for what this code does (shown to the owner).' },
      timeout_s: { type: 'number', description: `Seconds before the cell is interrupted (default ${Math.round(cfg.cellTimeoutMs / 1000)}).` },
    },
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
    async execute(args, exec) {
      if (!String(args.code || '').trim()) throw new Error('code must be non-empty');
      const k = await kernelFor(exec.agent);
      const timeoutMs = args.timeout_s > 0 ? Math.min(args.timeout_s * 1000, 6 * 3600_000) : cfg.cellTimeoutMs;
      return k.queue(() => k.cell(String(args.code), exec, timeoutMs));
    },
    presentCall: (args) => ({ card: 'generic', title: args.description || 'python', kind: 'execute', rawInput: args.code }),
  }));
  ctx.logger?.info?.(`walter-python: tool ${TOOL_NAME} registered (sandbox ${cfg.sandbox}, user ${cfg.user})`);
  return plugin;
}

export const __test = { Kernel };
