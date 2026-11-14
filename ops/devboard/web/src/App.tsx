import { useCallback, useEffect, useState } from "react";
import { api, useStream, type CardDetail, type DocInfo, type Live, type Summary, type VisionComponent } from "./api";
import { CardPanel } from "./components/CardPanel";
import { CommandK } from "./components/CommandK";
import { LiveBadge } from "./components/LiveBadge";
import { Sidebar, type View } from "./components/Sidebar";
import { Cards } from "./views/Cards";
import { Decisions } from "./views/Decisions";
import { Doc, DocOutline } from "./views/Doc";
import { Inbox } from "./views/Inbox";
import { Today } from "./views/Today";
import { Vision } from "./views/Vision";

/** Route in the hash: #/<view>?a=<arg>&n=<anchor>&s=<selected card>&by=module&r=1 */
type Route = { view: View; arg?: string; anchor?: string; sel?: string; by?: "status" | "module"; replaced?: boolean };
const VIEWS: View[] = ["inbox", "today", "cards", "decisions", "vision", "doc"];

function parse(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#\/?/, "").split("?");
  const p = new URLSearchParams(query);
  const view = (VIEWS as string[]).includes(path) ? (path as View) : "inbox";
  return { view, arg: p.get("a") ?? undefined, anchor: p.get("n") ?? undefined, sel: p.get("s") ?? undefined,
           by: p.get("by") === "module" ? "module" : "status", replaced: p.get("r") === "1" };
}

function format(r: Route): string {
  const p = new URLSearchParams();
  if (r.arg) p.set("a", r.arg);
  if (r.anchor) p.set("n", r.anchor);
  if (r.sel) p.set("s", r.sel);
  if (r.by === "module") p.set("by", "module");
  if (r.replaced) p.set("r", "1");
  const q = p.toString();
  return `#/${r.view}${q ? "?" + q : ""}`;
}

const TITLE: Record<View, string> = { inbox: "Attend ton accord", today: "Aujourd'hui", cards: "Chantiers",
                                      decisions: "Décisions", vision: "Carte de la vision", doc: "Document" };

export function App() {
  const [route, setRoute] = useState<Route>(() => parse(location.hash));
  const [tick, setTick] = useState(0);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [docs, setDocs] = useState<DocInfo[]>([]);
  const [vision, setVision] = useState<VisionComponent[]>([]);
  const [live, setLive] = useState<Live[]>([]);
  const [card, setCard] = useState<CardDetail | null>(null);
  const [search, setSearch] = useState(false);

  useEffect(() => {
    const on = () => setRoute(parse(location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = useCallback((r: Route) => { location.hash = format(r); }, []);

  useStream(() => setTick((t) => t + 1));
  useEffect(() => {
    api.summary().then(setSummary).catch(() => {});
    api.vision().then(setVision).catch(() => {});
    api.live().then(setLive).catch(() => {});
    api.docs().then(setDocs).catch(() => {});
  }, [tick]);
  useEffect(() => {
    if (!route.sel) { setCard(null); return; }
    api.card(route.sel).then(setCard).catch(() => setCard(null));
  }, [route.sel, tick]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearch((s) => !s); }
      else if (e.key === "Escape" && !search) go({ ...route, sel: undefined });
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [route, search, go]);

  const select = (ref: string) => go({ ...route, sel: ref });
  const openCard = (ref: string) => go({ view: route.view === "doc" ? "cards" : route.view, arg: route.view === "doc" ? undefined : route.arg,
                                         by: route.by, sel: ref });
  const openDoc = (path: string, anchor?: string) => go({ view: "doc", arg: path, anchor });
  const navigate = (view: View, arg?: string) => go({ view, arg });

  const doc = route.view === "doc" ? docs.find((d) => d.path === route.arg) : undefined;
  const heading = route.view === "doc" ? (route.arg === "reports" ? "Rapports" : doc?.title ?? "Document")
                : route.view === "cards" && route.arg ? `Chantiers · ${route.arg}` : TITLE[route.view];
  const tabs = route.view === "cards"
    ? [["Par état", route.by !== "module", () => go({ ...route, by: "status" })],
       ["Par module", route.by === "module", () => go({ ...route, by: "module" })]] as const
    : route.view === "decisions"
    ? [["Toutes", !route.replaced, () => go({ ...route, replaced: false })],
       ["Remplacées", !!route.replaced, () => go({ ...route, replaced: true })]] as const
    : [];

  return (
    <div className="grid h-screen grid-cols-[230px_1fr_400px] bg-black text-[13px] text-text">
      <Sidebar view={route.view} summary={summary} docs={docs} vision={vision} docPath={route.arg}
               onNavigate={navigate} onSearch={() => setSearch(true)} />
      <main className="flex min-w-0 flex-col overflow-hidden border-r border-line">
        <div className="flex items-center gap-3.5 border-b border-line px-[18px] py-3">
          <h1 className="text-[15px] font-semibold text-white">{heading}</h1>
          {tabs.map(([label, on, click]) => (
            <button key={label} type="button" onClick={click}
              className={`rounded-md border px-2.5 py-[3px] text-xs ${on ? "border-walter text-white" : "border-line2 text-soft hover:text-white"}`}>
              {label}
            </button>
          ))}
          <LiveBadge live={live} />
        </div>
        {summary?.pause && route.view !== "inbox" && (
          <p className="border-b border-line px-[18px] py-2 text-xs text-wait">
            Lecture des sessions en pause : le quota de l'abonnement Claude est trop haut. Elle reprend toute seule.
          </p>
        )}
        <div className="min-h-0 flex-1 overflow-auto">
          {route.view === "inbox" && <Inbox tick={tick} selected={route.sel} summary={summary} onSelect={select} />}
          {route.view === "today" && <Today tick={tick} onSelect={select} />}
          {route.view === "cards" && <Cards tick={tick} selected={route.sel} by={route.by ?? "status"} filter={route.arg} onSelect={select} />}
          {route.view === "decisions" && <Decisions tick={tick} replacedOnly={!!route.replaced} onOpenDoc={openDoc} />}
          {route.view === "vision" && <Vision vision={vision} onModule={(m) => navigate("cards", m)} />}
          {route.view === "doc" && route.arg && <Doc path={route.arg} anchor={route.anchor} docs={docs} onOpenDoc={openDoc} />}
        </div>
      </main>
      <aside className="overflow-auto px-[18px] py-4">
        {card ? <CardPanel card={card} ownerName={summary?.owner_name ?? ""} onOpenDoc={openDoc} onOpenCard={openCard} />
          : route.view === "doc" && route.arg && route.arg !== "reports" ? <DocOutline path={route.arg} docs={docs} onOpenDoc={openDoc} />
          : <p className="text-muted">Choisis un chantier pour voir son détail, ses décisions et ses preuves.</p>}
      </aside>
      <CommandK open={search} docs={docs} onClose={() => setSearch(false)} onOpenCard={openCard} onOpenDoc={openDoc} />
    </div>
  );
}
