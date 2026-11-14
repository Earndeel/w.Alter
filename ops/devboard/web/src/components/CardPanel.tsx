import type { CardDetail } from "../api";
import { ago, COMPONENT_LABEL, day, ddmm, dotKind, fileName, FIELD_LABEL, OWNER_LABEL, STATUS_LABEL } from "../labels";
import { Box } from "./Box";
import { StatusDot } from "./StatusDot";

type Props = { card: CardDetail; ownerName: string; onOpenDoc: (path: string, anchor?: string) => void;
               onOpenCard: (ref: string) => void };

function stateLabel(c: CardDetail): string {
  if (c.status === "waiting_owner") return STATUS_LABEL.waiting_owner + (c.flags.waiting_days ? ` depuis ${c.flags.waiting_days} j` : "");
  if (c.flags.late) return `En retard (prévu le ${ddmm(c.deadline)})`;
  if (c.flags.stale) return "Oublié : rien depuis " + ago(c.last_activity_at);
  return STATUS_LABEL[c.status];
}

export function CardPanel({ card: c, ownerName, onOpenDoc, onOpenCard }: Props) {
  const lastCorrection = c.corrections[0];
  const vision = [c.component ? COMPONENT_LABEL[c.component] ?? c.component : null, c.module].filter(Boolean).join(" › ");
  return (
    <div>
      <div className="mb-1 text-xs text-muted">{[c.ref, c.module, c.component && COMPONENT_LABEL[c.component]].filter(Boolean).join(" · ")}</div>
      <h2 className="mb-3 text-[17px] font-semibold text-white">{c.title}</h2>
      <div className="mb-3.5 grid grid-cols-[90px_1fr] gap-x-2.5 gap-y-1.5 text-xs">
        <div className="text-muted">État</div>
        <div className="flex items-center gap-1.5"><StatusDot kind={dotKind(c)} /> {stateLabel(c)}</div>
        <div className="text-muted">Vision</div><div>{vision || "—"}</div>
        <div className="text-muted">Porteur</div><div>{OWNER_LABEL[c.owner ?? ""] ?? "—"}</div>
        <div className="text-muted">Dates</div>
        <div>ouvert le {ddmm(c.created_at)} · actif le {ddmm(c.last_activity_at)}{c.deadline ? ` · prévu le ${ddmm(c.deadline)}` : ""}</div>
        {c.blocks.length > 0 && <><div className="text-muted">Bloque</div>
          <div>{c.blocks.map((b) => <button key={b.ref} type="button" className="mr-2 hover:text-walter" onClick={() => onOpenCard(b.ref)}>{b.ref} {b.title}</button>)}</div></>}
        {c.blocked_by.length > 0 && <><div className="text-muted">Bloqué par</div>
          <div>{c.blocked_by.map((b) => <button key={b.ref} type="button" className="mr-2 hover:text-walter" onClick={() => onOpenCard(b.ref)}>{b.ref} {b.title}</button>)}</div></>}
      </div>
      {c.corrected.length > 0 && lastCorrection && (
        <p className="mb-2 text-xs text-[#7fd8ff]">
          corrigé par {ownerName} le {ddmm(lastCorrection.at)} ({c.corrected.map((f) => FIELD_LABEL[f] ?? f).join(", ")})
        </p>
      )}
      <Box title="Ce que ça change"><p>{c.change || "—"}</p></Box>
      <Box title="Décisions liées">
        {c.decisions.length === 0 && <p className="text-muted">Aucune</p>}
        {c.decisions.map((d) => (
          <div key={d.anchor} className="py-1">
            {d.replaced_by.length > 0 ? (
              <>
                <button type="button" onClick={() => onOpenDoc(d.doc_path, d.anchor)}
                  className="text-left text-[#6b7b84] line-through">{d.title}</button>
                {d.replaced_by.map((n) => (
                  <div key={n.anchor}>
                    <span className="text-walter">→ </span>
                    <button type="button" onClick={() => onOpenDoc(d.doc_path, n.anchor)} className="text-left hover:text-walter">{n.title}</button>
                    <span className="text-xs text-muted"> · {ddmm(n.date)}</span>
                    {n.quote && <div className="pl-3 text-xs text-soft">« {n.quote} »</div>}
                  </div>
                ))}
              </>
            ) : (
              <button type="button" onClick={() => onOpenDoc(d.doc_path, d.anchor)} className="text-left hover:text-walter">
                {d.title} <span className="text-xs text-muted">· {ddmm(d.date)}</span>
              </button>
            )}
          </div>
        ))}
      </Box>
      <Box title="Fichiers">
        {c.files.length === 0 && <p className="text-muted">Aucun</p>}
        {c.files.map((f) => (
          <button key={f} type="button" title={f} onClick={() => onOpenDoc(f, undefined)}
            className="flex w-full justify-between border-b border-[#0d1a21] py-1 text-left last:border-0 hover:text-walter">
            <span><span className="text-walter">▤ </span>{fileName(f)}</span>
            <span className="text-xs text-muted">{f.split("/").slice(-3, -1).join("/")}</span>
          </button>
        ))}
      </Box>
      <Box title="Activité">
        {c.activity.map((a, i) => (
          <div key={i} className={`grid grid-cols-[52px_1fr] gap-2 border-b border-row py-1.5 text-xs last:border-0 ${i === 0 ? "text-[#7fd8ff]" : ""}`}>
            <span className="text-muted">{i === 0 ? "● " : ""}{ago(a.at)}</span><span>{a.text}</span>
          </div>
        ))}
      </Box>
      <Box title="Preuves">
        {c.evidence.slice(0, 8).map((e, i) => (
          <div key={i} className="border-b border-row py-1.5 text-xs last:border-0">
            <span className="text-soft">« {e.quote} »</span>
            <div className="text-muted">{e.kind === "commit" ? "commit" : e.kind === "task" ? "tâche" : "session"} · {day(e.at)}{e.seq != null ? ` · #${e.seq}` : ""}</div>
          </div>
        ))}
      </Box>
    </div>
  );
}
