import { useEffect, useState } from "react";
import { api, type Decision } from "../api";
import { ddmm } from "../labels";

export function Decisions({ tick, replacedOnly, onOpenDoc }: { tick: number; replacedOnly: boolean;
  onOpenDoc: (path: string, anchor?: string) => void }) {
  const [items, setItems] = useState<Decision[] | null>(null);
  useEffect(() => { api.decisions(replacedOnly).then(setItems).catch(() => setItems([])); }, [tick, replacedOnly]);
  return (
    <div>
      {items?.length === 0 && <p className="px-[18px] py-6 text-muted">{replacedOnly ? "Aucune décision remplacée pour l'instant." : "Aucune décision."}</p>}
      {items?.map((d) => (
        <div key={d.anchor} className="border-b border-row px-[18px] py-2">
          <button type="button" onClick={() => onOpenDoc(d.doc_path, d.anchor)}
            className={`grid w-full grid-cols-[52px_1fr] gap-2.5 text-left hover:text-walter ${d.replaced_by.length ? "text-[#6b7b84] line-through" : "text-bright"}`}>
            <span className="text-xs text-muted no-underline">{ddmm(d.date)}</span><span>{d.title}</span>
          </button>
          {d.replaced_by.map((n) => (
            <div key={n.anchor} className="ml-[62px] text-xs">
              <span className="text-walter">→ </span>remplacée le {ddmm(n.date)} par{" "}
              <button type="button" className="text-bright hover:text-walter" onClick={() => onOpenDoc(d.doc_path, n.anchor)}>{n.title}</button>
              {n.quote && <div className="text-soft">« {n.quote} »</div>}
            </div>
          ))}
          {d.replaces.length > 0 && !d.replaced_by.length && (
            <div className="ml-[62px] text-xs text-muted">remplace : {d.replaces.map((o) => o.title).join(" ; ")}</div>
          )}
        </div>
      ))}
    </div>
  );
}
