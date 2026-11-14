export const STATUS_LABEL: Record<string, string> = {
  waiting_owner: "Attend ton accord", in_progress: "En cours", late_or_stale: "Oublié · en retard",
  paused: "En pause", done: "Fini", abandoned: "Abandonné",
};
export const OWNER_LABEL: Record<string, string> = {
  owner: "toi", claude_code: "Claude Code", codex: "Codex", walter: "W.Alter",
};
export const RUNTIME_LABEL: Record<string, string> = { claude_code: "Claude Code", codex: "Codex" };
export const COMPONENT_LABEL: Record<string, string> = {
  core: "Core", cognition: "Cognition", capabilities: "Capabilities", ops: "Ops", lab: "Lab",
};
export const FIELD_LABEL: Record<string, string> = {
  status: "état", title: "titre", module: "module", owner: "porteur", change: "ce que ça change",
  deadline: "échéance", decision_link: "décision liée",
};
const MONTHS = ["janv", "févr", "mars", "avr", "mai", "juin", "juil", "août", "sept", "oct", "nov", "déc"];

/** « 14 nov » */
export function day(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? iso + "T12:00:00Z" : iso);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

/** « 14/11 » */
export function ddmm(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? iso + "T12:00:00Z" : iso);
  return `${String(d.getUTCDate()).padStart(2, "0")}/${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** « 2 min », « 3 h », « 4 j » */
export function ago(iso: string, now = Date.now()): string {
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `${Math.round(s / 3600)} h`;
  return `${Math.round(s / 86400)} j`;
}

export function fileName(path: string): string {
  return path.split("/").filter(Boolean).pop() ?? path;
}

/** The dot of a card: waiting, in progress, late/stale, done, paused/abandoned. */
export function dotKind(c: { status: string; flags: { late: boolean; stale: boolean } }): string {
  if (c.status === "waiting_owner") return "wait";
  if (c.flags.late || c.flags.stale) return "late";
  if (c.status === "in_progress") return "prog";
  if (c.status === "done") return "done";
  return "idle";
}
