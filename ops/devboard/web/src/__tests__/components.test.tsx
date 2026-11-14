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
  expect(FakeSource.last.url).toBe("/api/stream");
  act(() => FakeSource.last.listeners["change"](new MessageEvent("change", { data: "{}" })));
  expect(reload).toHaveBeenCalledTimes(1);
  vi.unstubAllGlobals();
});
