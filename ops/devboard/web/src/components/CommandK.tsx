import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Card, type Decision, type DocInfo } from "../api";
import { ddmm, dotKind } from "../labels";
import { StatusDot } from "./StatusDot";

type Hit = { key: string; kind: "Chantier" | "Décision" | "Document"; label: string; hint: string; dot?: string;
             go: () => void };
type Props = { open: boolean; docs: DocInfo[]; onClose: () => void; onOpenCard: (ref: string) => void;
               onOpenDoc: (path: string, anchor?: string) => void };

const norm = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

/** ⌘K: one box over the cards (server search), the decisions and the documents' sections. */
export function CommandK({ open, docs, onClose, onOpenCard, onOpenDoc }: Props) {
  const [q, setQ] = useState("");
  const [cards, setCards] = useState<Card[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [at, setAt] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQ(""); setAt(0);
    api.decisions().then(setDecisions).catch(() => setDecisions([]));
    setTimeout(() => input.current?.focus(), 0);
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      api.cards("status", q).then((gs) => setCards(gs.flatMap((g) => g.cards))).catch(() => setCards([]));
    }, 120);
    return () => clearTimeout(t);
  }, [open, q]);

  const hits = useMemo<Hit[]>(() => {
    const n = norm(q.trim());
    const match = (s: string) => !n || norm(s).includes(n);
    const out: Hit[] = cards.slice(0, 8).map((c) => ({ key: "c" + c.ref, kind: "Chantier", label: c.title,
      hint: [c.ref, c.module].filter(Boolean).join(" · "), dot: dotKind(c), go: () => onOpenCard(c.ref) }));
    if (n) {
      decisions.filter((d) => match(d.title)).slice(0, 6).forEach((d) => out.push({ key: "d" + d.anchor, kind: "Décision",
        label: d.title, hint: ddmm(d.date) + (d.replaced_by.length ? " · remplacée" : ""), go: () => onOpenDoc(d.doc_path, d.anchor) }));
      for (const doc of docs) {
        if (match(doc.title)) out.push({ key: "f" + doc.path, kind: "Document", label: doc.title, hint: doc.path,
                                          go: () => onOpenDoc(doc.path) });
        doc.sections.filter((s) => s.level <= 3 && match(s.heading)).slice(0, 3).forEach((s) => out.push({
          key: "s" + doc.path + s.anchor, kind: "Document", label: s.heading, hint: doc.title, go: () => onOpenDoc(doc.path, s.anchor) }));
        if (out.length > 30) break;
      }
    }
    return out.slice(0, 30);
  }, [q, cards, decisions, docs, onOpenCard, onOpenDoc]);

  if (!open) return null;
  const choose = (h?: Hit) => { if (h) { h.go(); onClose(); } };
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 pt-[12vh]" onClick={onClose}>
      <div role="dialog" aria-label="Chercher" onClick={(e) => e.stopPropagation()}
        className="w-[min(620px,92vw)] overflow-hidden rounded-lg border border-walter bg-black">
        <input ref={input} value={q} placeholder="Chercher un chantier, une décision, un document…"
          onChange={(e) => { setQ(e.target.value); setAt(0); }}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            else if (e.key === "ArrowDown") { e.preventDefault(); setAt((i) => Math.min(i + 1, hits.length - 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setAt((i) => Math.max(i - 1, 0)); }
            else if (e.key === "Enter") choose(hits[at]);
          }}
          className="w-full border-b border-line bg-black px-4 py-3 text-bright outline-none placeholder:text-muted" />
        <div className="max-h-[50vh] overflow-auto">
          {hits.length === 0 && <p className="px-4 py-3 text-muted">Rien trouvé.</p>}
          {hits.map((h, i) => (
            <button key={h.key} type="button" onMouseEnter={() => setAt(i)} onClick={() => choose(h)}
              className={`grid w-full grid-cols-[78px_1fr_auto] items-center gap-2.5 px-4 py-2 text-left ${i === at ? "bg-sel" : ""}`}>
              <span className="text-[11px] text-muted">{h.kind}</span>
              <span className="flex items-center gap-2 truncate text-bright">{h.dot && <StatusDot kind={h.dot} />}{h.label}</span>
              <span className="truncate text-[11px] text-muted">{h.hint}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
