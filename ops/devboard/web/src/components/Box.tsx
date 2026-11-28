import type { ReactNode } from "react";

/** An information card of the right panel: 1 px #01B7FF frame (owner's request, 2026-11-14). */
export function Box({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="my-2.5 rounded-lg border border-walter bg-black px-3 py-2.5">
      <h3 className="mb-1.5 text-xs uppercase tracking-[.05em] text-walter">{title}</h3>
      {children}
    </section>
  );
}
