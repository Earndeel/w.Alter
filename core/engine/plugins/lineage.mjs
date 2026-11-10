// W.Alter engine — who is the parent of an in-process sub-agent (lot E5, 2026-11-10).
// The kernel keeps a child's owner in its agent registry, not on the agent: what a plugin can read is the child
// session's header (`parentSession`, `delegationDepth`, `origin: 'subagent'`). Each plugin notes the headers it sees
// in one in-process map (child id → parent id), so the root of any descendant is found: a child is always seen
// (its first step) before it can spawn its own. Used by the policy (a child is judged under its root's door), the
// Engine API (a child's approvals go to its root's client) and the intake (a child's run is filed under its parent's).
const KEY = Symbol.for('walter.engine.lineage');

export function lineage() {
  if (!(globalThis[KEY] instanceof Map)) globalThis[KEY] = new Map();
  return globalThis[KEY];
}

/** Note the agent's parent (if any) and return its own session id. Test doubles may carry `parentAgent`. */
export function note(agent) {
  const h = agent?.session?.header;
  const parent = h?.parentSession || agent?.parentAgent?.session?.header?.id || null;
  if (agent?.parentAgent) note(agent.parentAgent);
  if (h?.id && parent) lineage().set(h.id, parent);
  return h?.id || null;
}

export const parentIdOf = (agent) => { const id = note(agent); return (id && lineage().get(id)) || null; };

/** The root session id of an agent (itself when it is no one's child). */
export function rootIdOf(agentOrId) {
  let id = agentOrId;
  if (typeof agentOrId !== 'string') {
    let a = agentOrId;
    note(a);
    while (a?.parentAgent) a = a.parentAgent;
    id = a?.session?.header?.id || null;
  }
  for (let i = 0; id && lineage().has(id) && i < 64; i += 1) id = lineage().get(id);
  return id;
}
