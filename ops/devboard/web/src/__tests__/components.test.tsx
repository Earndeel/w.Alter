import { act, render, screen } from "@testing-library/react";
import { CardRow } from "../components/CardRow";
import { CardPanel } from "../components/CardPanel";
import { Sidebar } from "../components/Sidebar";
import { LiveBadge } from "../components/LiveBadge";
import { useStream } from "../api";
import { card, detail } from "./fixtures";

test("CardRow affiche le numéro, le titre et le module", () => {
  render(<CardRow card={card} selected={false} onSelect={() => {}} />);
  expect(screen.getByText("W-12")).toBeInTheDocument();
  expect(screen.getByText("Activer le jeu de questions 3")).toBeInTheDocument();
  expect(screen.getByText("context")).toBeInTheDocument();
});

test("CardPanel barre l'ancienne décision et affiche la nouvelle avec sa date", () => {
  render(<CardPanel card={detail} ownerName="Camille" onOpenDoc={() => {}} onOpenCard={() => {}} />);
  const old = screen.getByText("Le modèle de décision choisit le spécialiste");
  expect(old).toHaveClass("line-through");
  expect(screen.getByText("Le L2 appelle des sous-agents")).toBeInTheDocument();
  expect(screen.getByText(/13\/11/)).toBeInTheDocument();
  expect(screen.getByText(/remplace le choix/)).toBeInTheDocument();
});

test("CardPanel signale une correction du propriétaire", () => {
  render(<CardPanel card={{ ...detail, corrected: ["status"] }} ownerName="Camille" onOpenDoc={() => {}}
                    onOpenCard={() => {}} />);
  expect(screen.getByText(/corrigé par Camille le 14\/11/)).toBeInTheDocument();
});

test("CardPanel ouvre un fichier dans la vue Doc", () => {
  const open = vi.fn();
  render(<CardPanel card={detail} ownerName="Camille" onOpenDoc={open} onOpenCard={() => {}} />);
  act(() => screen.getByText("VISION.md").click());
  expect(open).toHaveBeenCalledWith("/walter/docs/VISION.md", undefined);
});

test("Sidebar affiche le compteur de l'inbox", () => {
  render(<Sidebar view="inbox" summary={{ inbox: 4, open: 6, late_or_stale: 1, decisions: 170, replaced: 3, live: 0,
                                           pause: null, owner_name: "Camille" }}
                  docs={[]} vision={[]} onNavigate={() => {}} onSearch={() => {}} />);
  const nav = screen.getByText("Attend ton accord").closest("button")!;
  expect(nav).toHaveTextContent("4");
});

test("LiveBadge est masqué si rien n'est en direct", () => {
  const { container } = render(<LiveBadge live={[]} />);
  expect(container).toBeEmptyDOMElement();
  render(<LiveBadge live={[{ session_id: "s", runtime: "claude_code", title: "tableau", at: "2026-11-14T10:00:00Z",
                             ref: "W-1", card_title: "Tableau", module: "ops" }]} />);
  expect(screen.getByText(/Claude Code travaille sur/)).toBeInTheDocument();
});

class FakeSource {
  static last: FakeSource;
  listeners: Record<string, (e: MessageEvent) => void> = {};
  constructor(public url: string) { FakeSource.last = this; }
  addEventListener(type: string, fn: (e: MessageEvent) => void) { this.listeners[type] = fn; }
  close() {}
}

test("le flux en direct déclenche le rechargement", () => {
  vi.stubGlobal("EventSource", FakeSource);
  const reload = vi.fn();
  function Probe() { useStream(reload); return null; }
  render(<Probe />);
  expect(FakeSource.last.url).toBe("api/stream");
  act(() => FakeSource.last.listeners["change"](new MessageEvent("change", { data: "{}" })));
  expect(reload).toHaveBeenCalledTimes(1);
  vi.unstubAllGlobals();
});

test("CardPanel sans actions : pas de bouton, renvoi vers Walter Web", () => {
  render(<CardPanel card={detail} ownerName="Camille" onOpenDoc={() => {}} onOpenCard={() => {}} />);
  expect(screen.queryByText("Reprendre")).not.toBeInTheDocument();
  expect(screen.getByText(/depuis le panneau Développement de Walter Web/)).toBeInTheDocument();
});

test("Reprendre explique ce qui va se passer puis envoie la consigne", async () => {
  const calls: { url: string; body: string; headers: Record<string, string> }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, body: String(init.body), headers: init.headers as Record<string, string> });
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }));
  const changed = vi.fn();
  render(<CardPanel card={detail} ownerName="Camille" onOpenDoc={() => {}} onOpenCard={() => {}} actions onChanged={changed} />);
  act(() => screen.getByText("Reprendre").click());
  expect(screen.getByText(/Il vérifie d'abord l'état réel/)).toBeInTheDocument();
  expect(screen.getByText(/un message en votre nom/)).toBeInTheDocument();
  await act(async () => screen.getByText("Lancer la reprise").click());
  expect(calls[0].url).toBe("api/actions/resume");
  expect(JSON.parse(calls[0].body)).toEqual({ ref: "W-12", note: "" });
  expect(calls[0].headers["X-Walter-Action"]).toBe("1");
  expect(changed).toHaveBeenCalled();
  vi.unstubAllGlobals();
});

test("Une reprise en cours bloque un second clic", () => {
  const running = { ...detail, resumes: [{ id: 1, walter_session: "dsh/vm/x", note: null, status_before: "paused" as const,
    status: "running", outcome: null, summary: null, started_at: new Date().toISOString(), ended_at: null }] };
  render(<CardPanel card={running} ownerName="Camille" onOpenDoc={() => {}} onOpenCard={() => {}} actions />);
  expect(screen.getByText("Reprise en cours…")).toBeDisabled();
  expect(screen.getByText(/Reprise en cours depuis/)).toBeInTheDocument();
});
