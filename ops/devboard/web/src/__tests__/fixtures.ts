import type { Card, CardDetail } from "../api";

export const card: Card = {
  ref: "W-12", title: "Activer le jeu de questions 3", module: "context", status: "waiting_owner", owner: "owner",
  change: "Le modèle comprend le message.", deadline: null, waiting_since: "2026-11-10T10:00:00+00:00",
  created_at: "2026-11-10T10:00:00+00:00", updated_at: "2026-11-14T10:00:00+00:00",
  last_activity_at: "2026-11-14T10:00:00+00:00", flags: { late: false, waiting_days: 4, stale: false },
  component: "cognition", corrected: [],
};

export const detail: CardDetail = {
  ...card,
  decisions: [{
    anchor: "2026-11-01-ancienne", date: "2026-11-01", title: "Le modèle de décision choisit le spécialiste",
    doc_path: "/d/DECISIONS.md", removed: false, replaces: [],
    replaced_by: [{ anchor: "2026-11-13-nouvelle", date: "2026-11-13", title: "Le L2 appelle des sous-agents",
                    quote: "remplace le choix" }],
  }],
  files: ["/walter/docs/VISION.md"], blocks: [], blocked_by: [],
  evidence: [{ kind: "session", source_ref: "claude_code/vm/x", seq: 4, quote: "on active le jeu 3",
               at: "2026-11-14T10:00:00+00:00" }],
  activity: [{ at: "2026-11-14T10:00:00+00:00", kind: "reading", source_ref: "x", text: "W-12 créée" }],
  corrections: [{ field: "status", value: "waiting_owner", reason: "j'attends", by: "owner",
                  at: "2026-11-14T09:00:00+00:00" }],
};
