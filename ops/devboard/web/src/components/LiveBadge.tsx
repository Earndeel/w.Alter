import type { Live } from "../api";
import { RUNTIME_LABEL } from "../labels";

export function LiveBadge({ live }: { live: Live[] }) {
  if (live.length === 0) return null;
  const l = live[0];
  const what = l.module ?? l.card_title ?? l.title ?? "une session";
  return (
    <span className="ml-auto flex items-center text-xs text-[#7fd8ff]" title={l.title ?? ""}>
      <b className="mr-1.5 inline-block h-[7px] w-[7px] animate-pulse rounded-full bg-walter shadow-[0_0_8px_#01B7FF]" />
      En direct — {RUNTIME_LABEL[l.runtime] ?? l.runtime} travaille sur&nbsp;<u>{what}</u>
      {live.length > 1 && <span className="ml-1 text-muted">(+{live.length - 1})</span>}
    </span>
  );
}
