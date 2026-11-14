import { useEffect, useState } from "react";
import { api, type Activity } from "../api";
import { ago } from "../labels";

const KIND: Record<string, string> = { reading: "session", commit: "commit", correction: "correction" };

export function Today({ tick, onSelect }: { tick: number; onSelect: (ref: string) => void }) {
  const [items, setItems] = useState<Activity[] | null>(null);
  useEffect(() => { api.today().then(setItems).catch(() => setItems([])); }, [tick]);
  return (
    <div>
      {items?.length === 0 && <p className="px-[18px] py-6 text-muted">Rien encore aujourd'hui.</p>}
      {items?.map((a, i) => (
        <button key={i} type="button" disabled={!a.ref} onClick={() => a.ref && onSelect(a.ref)}
          className={`grid w-full grid-cols-[60px_80px_1fr] gap-2.5 border-b border-row px-[18px] py-2 text-left ${i === 0 ? "text-[#7fd8ff]" : ""} ${a.ref ? "hover:bg-[#050f15]" : ""}`}>
          <span className="text-xs text-muted">{ago(a.at)}</span>
          <span className="text-[11px] text-[#7d97a5]">{KIND[a.kind] ?? a.kind}</span>
          <span className="truncate">{a.text}{a.title && !a.text.includes(a.title) ? <span className="text-muted"> — {a.title}</span> : null}</span>
        </button>
      ))}
    </div>
  );
}
