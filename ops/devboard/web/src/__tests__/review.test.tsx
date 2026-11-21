import { render, screen, waitFor } from "@testing-library/react";
import { LiveBadge } from "../components/LiveBadge";
import { Decisions } from "../views/Decisions";

test("LiveBadge ne montre jamais le titre brut d'une session (contenu possiblement personnel)", () => {
  const { container } = render(<LiveBadge live={[{ session_id: "s", runtime: "codex", title: "mon rendez-vous médical",
                                                   at: "2026-11-14T10:00:00Z", ref: null, card_title: null, module: null }]} />);
  expect(container.textContent).not.toContain("rendez-vous");
  expect(container.innerHTML).not.toContain("rendez-vous");
  expect(screen.getByText(/Codex travaille/)).toBeInTheDocument();
});

test("Une décision retirée du document reste visible et le dit", async () => {
  globalThis.fetch = (async () => new Response(JSON.stringify([
    { anchor: "a", date: "2026-11-01", title: "Ancienne règle", doc_path: "/d/DECISIONS.md", removed: true,
      replaces: [], replaced_by: [] }]))) as typeof fetch;
  render(<Decisions tick={0} replacedOnly={false} onOpenDoc={() => {}} />);
  await waitFor(() => expect(screen.getByText(/retirée du document/)).toBeInTheDocument());
});
