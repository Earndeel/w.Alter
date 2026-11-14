import { useEffect, useRef } from "react";

export type Status = "waiting_owner" | "in_progress" | "paused" | "done" | "abandoned";
export type Flags = { late: boolean; waiting_days: number | null; stale: boolean };
export type Card = {
  ref: string; title: string; module: string | null; status: Status; owner: string | null; change: string | null;
  deadline: string | null; waiting_since: string | null; created_at: string; updated_at: string;
  last_activity_at: string; flags: Flags; component: string | null; corrected: string[];
};
export type DecisionLink = { anchor: string; date: string; title: string; quote: string | null };
export type Decision = {
  anchor: string; date: string; title: string; doc_path: string; removed: boolean;
  replaces: DecisionLink[]; replaced_by: DecisionLink[];
};
export type Evidence = { kind: string; source_ref: string; seq: number | null; quote: string | null; at: string };
export type Activity = { at: string; kind: string; source_ref: string | null; text: string; ref?: string | null;
                         title?: string | null; module?: string | null };
export type Correction = { field: string; value: unknown; reason: string | null; by: string; at: string };
export type CardDetail = Card & {
  decisions: Decision[]; files: string[]; blocks: Pick<Card, "ref" | "title" | "status">[];
  blocked_by: Pick<Card, "ref" | "title" | "status">[]; evidence: Evidence[]; activity: Activity[];
  corrections: Correction[];
};
export type Group = { key: string; label: string; component?: string | null; cards: Card[] };
export type Summary = { inbox: number; open: number; late_or_stale: number; decisions: number; replaced: number;
                        live: number; pause: { what: string; at: string } | null; owner_name: string };
export type VisionModule = { id: string; path: string; health: string | null; color: "red" | "amber" | "green" | "blue";
                             counts: Record<string, number> };
export type VisionComponent = { key: string; label: string; modules: VisionModule[] };
export type Live = { session_id: string; runtime: string; title: string | null; at: string; ref: string | null;
                     card_title: string | null; module: string | null };
export type DocSection = { anchor: string; heading: string; level: number; line: number };
export type DocInfo = { path: string; title: string; kind: string; mtime: string | null; sections: DocSection[] };
export type DocText = { path: string; title: string; kind: string; anchor: string | null; markdown: string };

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json() as Promise<T>;
}

export const api = {
  summary: () => get<Summary>("/api/summary"),
  inbox: () => get<Card[]>("/api/inbox"),
  cards: (group: "status" | "module", q = "") =>
    get<Group[]>(`/api/cards?group=${group}&q=${encodeURIComponent(q)}`),
  card: (ref: string) => get<CardDetail>(`/api/cards/${encodeURIComponent(ref)}`),
  today: () => get<Activity[]>("/api/today"),
  decisions: (replaced = false) => get<Decision[]>(`/api/decisions${replaced ? "?replaced=1" : ""}`),
  vision: () => get<VisionComponent[]>("/api/vision"),
  live: () => get<Live[]>("/api/live"),
  docs: () => get<DocInfo[]>("/api/docs"),
  doc: (path: string, anchor?: string) =>
    get<DocText>(`/api/docs${path.split("/").map(encodeURIComponent).join("/")}` +
                 (anchor ? `?anchor=${encodeURIComponent(anchor)}` : "")),
};

/** Calls `onChange` on every `change` event of the live stream (the board was written to). */
export function useStream(onChange: () => void): void {
  const cb = useRef(onChange);
  cb.current = onChange;
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const es = new EventSource("/api/stream");
    es.addEventListener("change", () => cb.current());
    return () => es.close();
  }, []);
}
