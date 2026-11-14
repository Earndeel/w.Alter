import type { DocInfo, Summary, VisionComponent } from "../api";
import { ddmm } from "../labels";

export type View = "inbox" | "today" | "cards" | "decisions" | "vision" | "doc";
type Props = { view: View; summary: Summary | null; docs: DocInfo[]; vision: VisionComponent[]; docPath?: string;
               onNavigate: (view: View, arg?: string) => void; onSearch: () => void };

const MAIN_DOCS: [string, string][] = [["vision", "VISION"], ["decisions", "DECISIONS"], ["v1", "V1 — critère"],
                                       ["architecture", "ARCHITECTURE"], ["runbook", "RUNBOOK"]];
const COLOUR: Record<string, string> = { red: "text-late", amber: "text-wait", green: "text-ok", blue: "text-walter" };

function Nav({ on, label, count, badge, onClick, tone }: { on: boolean; label: string; count?: number | string;
  badge?: boolean; onClick: () => void; tone?: string }) {
  return (
    <button type="button" onClick={onClick}
      className={`flex w-full justify-between rounded-md px-2 py-[5px] text-left ${on ? "bg-hover shadow-[inset_2px_0_#01B7FF]" : "hover:bg-hover"} ${tone ?? (on ? "text-white" : "text-[#b6c6cf] hover:text-white")}`}>
      <span>{label}</span>
      {count !== undefined && count !== 0 && (badge
        ? <span className="rounded-[9px] bg-[#3a2a05] px-[7px] text-[11px] text-[#ffc34d]">{count}</span>
        : <span className="text-[11px] text-[#7d97a5]">{count}</span>)}
    </button>
  );
}

export function Sidebar({ view, summary, docs, vision, docPath, onNavigate, onSearch }: Props) {
  const reports = docs.filter((d) => d.kind === "report");
  const latest = reports.map((d) => d.mtime).filter(Boolean).sort().pop();
  return (
    <aside className="overflow-auto border-r border-line px-2.5 py-3.5">
      <div className="mx-1.5 mb-3.5 flex items-center gap-2 font-semibold text-white">
        <i className="inline-block h-[18px] w-[18px] rounded-[5px] border-2 border-walter" />W.Alter · Développement
      </div>
      <button type="button" onClick={onSearch}
        className="mx-1 mb-3.5 flex w-[calc(100%-8px)] justify-between rounded-md border border-line2 px-2 py-1.5 text-muted">
        <span>Chercher…</span><span>⌘K</span>
      </button>
      <Nav on={view === "inbox"} label="Attend ton accord" count={summary?.inbox ?? 0} badge onClick={() => onNavigate("inbox")} />
      <Nav on={view === "today"} label="Aujourd'hui" onClick={() => onNavigate("today")} />
      <Nav on={view === "cards"} label="Chantiers" count={summary?.open} onClick={() => onNavigate("cards")} />
      <Nav on={view === "decisions"} label="Décisions" count={summary?.decisions} onClick={() => onNavigate("decisions")} />
      <Nav on={view === "vision"} label="Carte de la vision" onClick={() => onNavigate("vision")} />
      <div className="mx-2 mb-1 mt-3.5 text-[11px] uppercase tracking-[.06em] text-muted">Documents</div>
      {MAIN_DOCS.map(([kind, label]) => {
        const d = docs.find((x) => x.kind === kind);
        return d ? <Nav key={kind} on={view === "doc" && docPath === d.path} label={"▤ " + label} onClick={() => onNavigate("doc", d.path)} /> : null;
      })}
      {reports.length > 0 && <Nav on={view === "doc" && reports.some((r) => r.path === docPath)} label="▤ Rapports"
        count={latest ? ddmm(latest) : reports.length} onClick={() => onNavigate("doc", "reports")} />}
      <div className="mx-2 mb-1 mt-3.5 text-[11px] uppercase tracking-[.06em] text-muted">Modules</div>
      {vision.flatMap((c) => c.modules).map((m) => (
        <Nav key={m.id} on={false} label={"◆ " + m.id} tone={COLOUR[m.color]} onClick={() => onNavigate("cards", m.id)} />
      ))}
    </aside>
  );
}
