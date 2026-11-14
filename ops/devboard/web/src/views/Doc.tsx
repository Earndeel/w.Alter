import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type DocInfo, type DocText } from "../api";
import { ddmm } from "../labels";

export function Doc({ path, anchor, docs, onOpenDoc }: { path: string; anchor?: string; docs: DocInfo[];
  onOpenDoc: (path: string, anchor?: string) => void }) {
  const [doc, setDoc] = useState<DocText | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (path === "reports") return;
    setError(false);
    api.doc(path, anchor).then(setDoc).catch(() => setError(true));
  }, [path, anchor]);
  if (path === "reports") {
    const reports = docs.filter((d) => d.kind === "report").sort((a, b) => (b.mtime ?? "").localeCompare(a.mtime ?? ""));
    return (
      <div>{reports.map((r) => (
        <button key={r.path} type="button" onClick={() => onOpenDoc(r.path)}
          className="grid w-full grid-cols-[52px_1fr] gap-2.5 border-b border-row px-[18px] py-2 text-left hover:bg-[#050f15]">
          <span className="text-xs text-muted">{ddmm(r.mtime)}</span><span className="truncate text-bright">{r.title}</span>
        </button>))}
      </div>
    );
  }
  if (error) return <p className="px-[18px] py-6 text-muted">Ce document n'est pas suivi par le tableau.</p>;
  if (!doc) return null;
  return (
    <article className="md px-[22px] py-4">
      {anchor && <button type="button" className="mb-3 text-xs text-walter" onClick={() => onOpenDoc(path)}>Voir tout le document</button>}
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{doc.markdown}</ReactMarkdown>
    </article>
  );
}

export function DocOutline({ path, docs, onOpenDoc }: { path: string; docs: DocInfo[];
  onOpenDoc: (path: string, anchor?: string) => void }) {
  const d = docs.find((x) => x.path === path);
  if (!d) return null;
  return (
    <div>
      <div className="mb-1 text-xs text-muted">{d.kind} · {path}</div>
      <h2 className="mb-3 text-[17px] font-semibold text-white">{d.title}</h2>
      <section className="rounded-lg border border-walter px-3 py-2.5">
        <h3 className="mb-1.5 text-xs uppercase tracking-[.05em] text-walter">Sections</h3>
        {d.sections.filter((s) => s.level <= 3).map((s) => (
          <button key={s.anchor} type="button" onClick={() => onOpenDoc(path, s.anchor)}
            className="block w-full truncate py-0.5 text-left text-xs hover:text-walter" style={{ paddingLeft: (s.level - 1) * 10 }}>
            {s.heading}
          </button>
        ))}
      </section>
    </div>
  );
}
