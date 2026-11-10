// W.Alter Engine API — address table (lot E4, 2026-11-10).
// An interface names a conversation `<door>/<account>/<conversation>`; the engine runs it in ONE kernel session.
// This table only maps the first to the second (no second session system): the kernel keeps history, writer lock,
// resume; Walter keeps its key `dsh/vm/<kernel id>` everywhere (runs, walter_logs, skills).
// The door of a kernel session is published in-process for the execution policy (core/security), so a Telegram or
// API session is judged under its own preset and its subagents under the same root door.
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

export const DOORS = ['web', 'telegram', 'api', 'mcp', 'command', 'schedule', 'webhook', 'lab'];
export const SESSION_ID = /^(web|telegram|api|mcp|command|schedule|webhook|lab)\/[A-Za-z0-9._:@/-]{1,200}$/;
const PART = /^[A-Za-z0-9._:@-]{1,100}$/;
const DOORS_KEY = Symbol.for('walter.engine.doors');

/** The in-process map kernel session id → door, read by the policy plugin (`interfaceOf`). */
export function doors() {
  if (!(globalThis[DOORS_KEY] instanceof Map)) globalThis[DOORS_KEY] = new Map();
  return globalThis[DOORS_KEY];
}

/** `<door>/<account>/<conversation>`, validated against engine-api.v1 `session_id`. */
export function engineSessionId(door, account, conversation) {
  if (!DOORS.includes(door)) throw new RangeError(`unknown interface ${door}`);
  if (!PART.test(String(account || ''))) throw new RangeError('principal id must match [A-Za-z0-9._:@-]{1,100}');
  if (!PART.test(String(conversation || ''))) throw new RangeError('conversation must match [A-Za-z0-9._:@-]{1,100}');
  const id = `${door}/${account}/${conversation}`;
  if (!SESSION_ID.test(id)) throw new RangeError('invalid session id');
  return id;
}

/** The door that judges a session: a command-mode session is a `command` session whatever opened it. */
export const effectiveDoor = (iface, mode) => (mode === 'command' ? 'command' : iface);

export class Bindings {
  constructor(file) { this.file = file; this.rows = {}; }

  load() {
    try { this.rows = JSON.parse(readFileSync(this.file, 'utf8')).sessions || {}; }
    catch (e) { if (e.code !== 'ENOENT') throw e; this.rows = {}; }
    for (const row of Object.values(this.rows)) doors().set(row.kernel, row.door);
    return this;
  }

  get(id) { return this.rows[id] || null; }

  byKernel(kernelId) { return Object.values(this.rows).find((r) => r.kernel === kernelId) || null; }

  list({ iface, account } = {}) {
    return Object.values(this.rows).filter((r) => (!iface || r.interface === iface) && (!account || r.principal?.id === account));
  }

  set(row) {
    this.rows[row.session_id] = row;
    doors().set(row.kernel, row.door);
    this.save();
    return row;
  }

  save() {   // atomic: never a half-written table
    mkdirSync(dirname(this.file), { recursive: true, mode: 0o700 });
    const tmp = `${this.file}.tmp-${process.pid}`;
    writeFileSync(tmp, `${JSON.stringify({ version: 1, sessions: this.rows }, null, 1)}\n`, { mode: 0o600 });
    renameSync(tmp, this.file);
  }
}
