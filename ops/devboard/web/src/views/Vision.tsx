import type { VisionComponent } from "../api";

const FRAME: Record<string, string> = { red: "border-late", amber: "border-wait", green: "border-ok", blue: "border-walter" };
const TEXT: Record<string, string> = { red: "text-late", amber: "text-wait", green: "text-ok", blue: "text-walter" };
const SAY: Record<string, string> = { red: "un chantier oublié ou en retard", amber: "attend ton accord",
                                      green: "tout est fini", blue: "rien de bloquant" };

export function Vision({ vision, onModule }: { vision: VisionComponent[]; onModule: (id: string) => void }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3 p-[18px]">
      {vision.map((c) => (
        <section key={c.key} className="rounded-lg border border-line2 p-3">
          <h3 className="mb-2 text-xs uppercase tracking-[.05em] text-walter">{c.label}</h3>
          {c.modules.length === 0 && <p className="text-xs text-muted">Aucun module</p>}
          {c.modules.map((m) => (
            <button key={m.id} type="button" onClick={() => onModule(m.id)}
              className={`mb-2 block w-full rounded-md border bg-black px-2.5 py-2 text-left ${FRAME[m.color]}`}>
              <div className="flex justify-between"><span className="text-white">{m.id}</span>
                <span className={`text-[11px] ${TEXT[m.color]}`}>{SAY[m.color]}</span></div>
              <div className="mt-1 text-[11px] text-muted">
                {[["waiting_owner", "attend"], ["in_progress", "en cours"], ["late_or_stale", "oublié"], ["done", "fini"]]
                  .filter(([k]) => m.counts[k]).map(([k, l]) => `${m.counts[k]} ${l}`).join(" · ") || "aucun chantier"}
                {m.health && m.health !== "active" ? ` · service ${m.health}` : ""}
              </div>
            </button>
          ))}
        </section>
      ))}
    </div>
  );
}
