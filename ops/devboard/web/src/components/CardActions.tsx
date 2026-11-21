import { useState } from "react";
import { api, type CardDetail, type Resume } from "../api";
import { ago, ddmm, STATUS_LABEL } from "../labels";

const RESUME_STATUS: Record<string, string> = {
  running: "en cours", ok: "terminée", cancelled: "interrompue", budget_exhausted: "arrêtée (plafond)",
  error: "en erreur", interrupted: "coupée (moteur arrêté)", unknown_outcome: "sans issue connue", lost: "perdue",
};

type Props = { card: CardDetail; enabled: boolean; onDone: () => void };

/** The owner's two buttons (2026-11-15). Shown only where the board can act (inside Walter Web). */
export function CardActions({ card: c, enabled, onDone }: Props) {
  const [open, setOpen] = useState<"resume" | "abandon" | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const running = c.resumes.find((r) => r.status === "running");
  const last = c.resumes[0];

  const send = async () => {
    setBusy(true); setError(null);
    try {
      if (open === "resume") await api.resume(c.ref, text);
      else await api.abandon(c.ref, text);
      setOpen(null); setText(""); onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="mb-3">
      {running && <ResumeLine r={running} />}
      {!running && last && <ResumeLine r={last} />}
      {enabled ? (
        <div className="flex gap-2">
          <button type="button" disabled={!!running || busy} onClick={() => { setOpen("resume"); setText(""); setError(null); }}
            className="rounded-md border-2 border-walter px-3 py-1 text-xs text-white hover:bg-sel disabled:opacity-40">
            {running ? "Reprise en cours…" : "Reprendre"}
          </button>
          {c.status !== "abandoned" && (
            <button type="button" disabled={busy} onClick={() => { setOpen("abandon"); setText(""); setError(null); }}
              className="rounded-md border-2 border-line2 px-3 py-1 text-xs text-soft hover:border-late hover:text-white">
              Abandonner
            </button>
          )}
        </div>
      ) : (
        <p className="text-xs text-muted">Reprendre / Abandonner : depuis le panneau Développement de Walter Web.</p>
      )}
      {open && (
        <div role="dialog" aria-label={open === "resume" ? "Reprendre" : "Abandonner"}
          className="mt-2.5 rounded-lg border-2 border-walter bg-black px-3 py-2.5 text-xs">
          {open === "resume" ? (
            <>
              <p className="mb-1.5 text-white">Ce qui va se passer</p>
              <ul className="mb-2 list-disc space-y-0.5 pl-4 text-soft">
                <li>Walter ouvre la conversation de ce chantier dans Walter Web (la même à chaque reprise de {c.ref}) avec
                  ce que le tableau sait : preuves, historique, décisions, fichiers.</li>
                <li>Il vérifie d'abord l'état réel, puis fait ce qui reste, avec votre accès complet.</li>
                <li>Il s'arrête et vous demande avant : un lot du moteur, un choix d'architecture, de données ou de
                  budget, une suppression, un message en votre nom.</li>
                <li>À la fin : la carte passe à fini, attend votre accord ou reste en cours, et vous recevez un mot sur
                  Telegram.</li>
              </ul>
              <label className="mb-1 block text-muted" htmlFor="resume-note">Consigne pour Walter (facultatif)</label>
            </>
          ) : (
            <>
              <p className="mb-1.5 text-white">Abandonner {c.ref}</p>
              <p className="mb-2 text-soft">La carte passe dans « Abandonné » et ne revient plus en cours (une lecture des
                sessions ne peut pas la rouvrir). « Reprendre » reste possible plus tard.{running ? " La reprise en cours est interrompue." : ""}</p>
              <label className="mb-1 block text-muted" htmlFor="resume-note">Pourquoi (facultatif)</label>
            </>
          )}
          <textarea id="resume-note" value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={2000}
            className="mb-2 w-full rounded-md border-2 border-line2 bg-black px-2 py-1 text-text focus:border-walter focus:outline-none"
            placeholder={open === "resume" ? "ex. : ok pour P1, commence par le backfill" : "ex. : fait ailleurs"} />
          {error && <p className="mb-2 text-late">{error}</p>}
          <div className="flex gap-2">
            <button type="button" disabled={busy} onClick={send}
              className={`rounded-md border-2 px-3 py-1 text-white disabled:opacity-40 ${open === "resume" ? "border-walter" : "border-late"}`}>
              {busy ? "…" : open === "resume" ? "Lancer la reprise" : "Abandonner"}
            </button>
            <button type="button" disabled={busy} onClick={() => setOpen(null)}
              className="rounded-md border-2 border-line2 px-3 py-1 text-soft hover:text-white">Annuler</button>
          </div>
        </div>
      )}
    </div>
  );
}

function ResumeLine({ r }: { r: Resume }) {
  return (
    <div className="mb-2 rounded-lg border border-walter px-3 py-2 text-xs">
      <div className={r.status === "running" ? "text-[#7fd8ff]" : "text-soft"}>
        {r.status === "running" ? "● " : ""}Reprise {RESUME_STATUS[r.status] ?? r.status}
        {r.status === "running" ? ` depuis ${ago(r.started_at)}` : ` le ${ddmm(r.ended_at ?? r.started_at)}`}
        {r.outcome ? ` · carte ${STATUS_LABEL[r.outcome]?.toLowerCase() ?? r.outcome}` : ""}
      </div>
      {r.status === "running" && <div className="text-muted">Suivre ou guider : dans Walter Web, la conversation de ce chantier.</div>}
      {r.summary && r.status !== "running" && <p className="mt-1 whitespace-pre-line text-soft">{r.summary.slice(0, 600)}</p>}
    </div>
  );
}
