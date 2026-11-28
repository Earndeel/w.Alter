import { useEffect, useState } from "react";
import { api, type Group } from "../api";
import { CardRow } from "../components/CardRow";
import { StatusDot } from "../components/StatusDot";

const DOT: Record<string, string> = { waiting_owner: "wait", in_progress: "prog", late_or_stale: "late", paused: "idle",
                                      done: "done", abandoned: "idle" };

export function Cards({ tick, selected, onSelect, by, filter }: { tick: number; selected?: string; by: "status" | "module";
  filter?: string; onSelect: (ref: string) => void }) {
  const [groups, setGroups] = useState<Group[] | null>(null);
  useEffect(() => { api.cards(by, filter ?? "").then(setGroups).catch(() => setGroups([])); }, [tick, by, filter]);
  const visible = (groups ?? []).filter((g) => g.cards.length > 0);
  return (
    <div>
      {groups && visible.length === 0 && <p className="px-[18px] py-6 text-muted">Aucun chantier{filter ? ` pour « ${filter} »` : ""}.</p>}
      {visible.map((g) => (
        <div key={g.key}>
          <div className="flex items-center gap-2 border-b border-[#0d1a21] bg-band px-[18px] pb-1 pt-2.5 text-xs text-soft">
            {by === "status" && <StatusDot kind={DOT[g.key]} />}{g.label} <span className="text-muted">{g.cards.length}</span>
          </div>
          {g.cards.map((c) => <CardRow key={c.ref} card={c} selected={c.ref === selected} onSelect={onSelect} />)}
        </div>
      ))}
    </div>
  );
}
