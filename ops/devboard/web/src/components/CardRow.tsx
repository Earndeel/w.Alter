import type { Card } from "../api";
import { day, dotKind, OWNER_LABEL } from "../labels";
import { StatusDot } from "./StatusDot";

export function CardRow({ card, selected, onSelect }: { card: Card; selected: boolean; onSelect: (ref: string) => void }) {
  const when = card.status === "waiting_owner" && card.flags.waiting_days != null
    ? `${card.flags.waiting_days} j` : day(card.last_activity_at);
  return (
    <button type="button" onClick={() => onSelect(card.ref)}
      className={`grid w-full grid-cols-[22px_62px_1fr_auto_auto_70px] items-center gap-2.5 border-b border-row px-[18px] py-2 text-left
        ${selected ? "bg-sel shadow-[inset_2px_0_#01B7FF]" : "hover:bg-[#050f15]"}`}>
      <StatusDot kind={dotKind(card)} />
      <span className="text-xs text-muted">{card.ref}</span>
      <span className="truncate text-bright">{card.title}</span>
      {card.module ? <span className="rounded-[10px] border border-line2 px-2 text-[11px] text-[#9fb5c1]">{card.module}</span> : <span />}
      <span className="text-[11px] text-[#7d97a5]">{OWNER_LABEL[card.owner ?? ""] ?? "—"}</span>
      <span className="text-right text-xs text-muted" title={card.status === "waiting_owner" ? "attend depuis" : "dernière activité"}>{when}</span>
    </button>
  );
}
