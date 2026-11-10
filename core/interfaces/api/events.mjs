// W.Alter Engine API — what a client sees of a session (lot E4, 2026-11-10).
// Pure functions over the kernel's durable session events (`SessionWireEvent`: type, seq, time, data), so the
// stream and the result of a turn are computed the same way live and after a restart (the log is the truth).

const textOf = (message) => (message?.content || [])
  .filter((b) => b && b.type === 'text' && typeof b.text === 'string').map((b) => b.text).join('');

/** One kernel event → one client event (or null when the client has no use for it). Ids and text only. */
export function toClientEvent(ev) {
  const d = ev?.data || {};
  const base = { seq: ev.seq, at: ev.time };
  switch (ev?.type) {
    case 'turn/start': return { ...base, type: 'turn.started', turn: d.turn };
    case 'turn/end': return { ...base, type: 'turn.ended', turn: d.turn, status: turnStatus(d.reason), reason: reasonOf(d.reason) };
    case 'user/message': {
      const src = d.source || {};
      if (src.kind !== 'user') return null;                 // runtime notices, injected context: not the owner's
      return { ...base, type: 'message.user', request_id: src.rpcId ?? null, text: textOf(d) };
    }
    case 'assistant/message': {
      const text = textOf(d.message);
      return text ? { ...base, type: 'message.assistant', turn: d.turn, step: d.step, text } : null;
    }
    case 'tool/call': return { ...base, type: 'tool.called', turn: d.turn, name: d.name, call_id: d.callId };
    case 'tool/result': return { ...base, type: 'tool.result', turn: d.turn, ok: !d.error };
    case 'approval/asked': return { ...base, type: 'approval.requested', request_id: d.id, tool: d.toolName, reason: d.reason ?? null };
    case 'approval/decided': return { ...base, type: 'approval.answered', request_id: d.id, outcome: d.outcome };
    default: return null;
  }
}

/** Status of a turn end in engine-event.v1 words. The kernel's reason is `{kind}`: completed | aborted | blocked
 *  (an archived session or Walter's turn budget) | error | max-tokens | interrupted (process gone) | forked. */
export function turnStatus(reason) {
  const kind = typeof reason === 'string' ? reason : reason?.kind;
  return { completed: 'ok', forked: 'ok', 'max-tokens': 'ok', aborted: 'cancelled', blocked: 'budget_exhausted',
    error: 'error', interrupted: 'interrupted' }[kind] || (kind ? 'unknown_outcome' : 'ok');
}

/** Why, in a few words a client can show (never the provider's raw error body). */
export const reasonOf = (reason) => (typeof reason === 'string' ? reason : reason?.kind ?? null);

/** The error code of a failed turn (e.g. INVALID_REQUEST), never its message: provider bodies may echo inputs. */
export const errorOf = (reason) => (reason?.kind === 'error' && reason.error?.code ? String(reason.error.code).slice(0, 60) : null);

/**
 * Follows one request through the log: the turn that received the owner message carrying `requestId`
 * (the kernel echoes the prompt's requestId as the user source's rpcId), its last answer, its tools, its end.
 * Feed events in seq order; `done` once that turn has ended.
 */
export class TurnWatch {
  constructor(requestId) {
    this.requestId = requestId;
    this.turn = null; this.current = null; this.pendingStart = false;
    this.text = ''; this.tools = []; this.done = false; this.reason = null; this.endSeq = null; this.error = null;
  }

  feed(ev) {
    if (this.done || !ev) return this;
    const d = ev.data || {};
    if (ev.type === 'turn/start') {
      this.current = d.turn;
      if (this.pendingStart) { this.turn = d.turn; this.pendingStart = false; }
    } else if (ev.type === 'turn/end' && this.current === d.turn) {
      if (this.turn === d.turn) {
        this.done = true; this.reason = reasonOf(d.reason); this.endSeq = ev.seq;
        this.error = errorOf(d.reason);
      }
      this.current = null;
    } else if (ev.type === 'user/message' && this.turn === null && d.source?.rpcId === this.requestId) {
      if (this.current !== null) this.turn = this.current;  // inside a turn (new turn or steering)
      else this.pendingStart = true;                       // queued: counts for the next turn
    } else if (this.turn !== null && d.turn === this.turn) {
      if (ev.type === 'assistant/message') { const t = textOf(d.message); if (t) this.text = t; }
      else if (ev.type === 'tool/call') this.tools.push(d.name);
    }
    return this;
  }

  result() {
    return { done: this.done, turn: this.turn, status: this.done ? turnStatus(this.reason) : 'running',
      reason: this.reason, ...(this.error ? { error: this.error } : {}), text: this.text, tools: this.tools, seq: this.endSeq };
  }
}
