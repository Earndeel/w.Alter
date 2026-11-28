import { useEffect, useState } from "react";
import { api, type Card, type Summary } from "../api";
import { CardRow } from "../components/CardRow";
import { StatusDot } from "../components/StatusDot";

export function Inbox({ tick, selected, onSelect, summary }: { tick: number; selected?: string; summary: Summary | null;
  onSelect: (ref: string) => void }) {
  const [cards, setCards] = useState<Card[] | null>(null);
  useEffect(() => { api.inbox().then(setCards).catch(() => setCards([])); }, [tick]);
  return (
    <div>
      {summary?.pause && (
        <p className="border-b border-line px-[18px] py-2 text-xs text-wait">
          Lecture des sessions en pause : le quota de l'abonnement Claude est trop haut. Elle reprend toute seule.
        </p>
      )}
      <div className="flex items-center gap-2 border-b border-[#0d1a21] bg-band px-[18px] pb-1 pt-2.5 text-xs text-soft">
        <StatusDot kind="wait" />Attend ton accord <span className="text-muted">{cards?.length ?? ""}</span>
      </div>
      {cards?.length === 0 && <p className="px-[18px] py-6 text-muted">Rien n'attend ton accord.</p>}
      {cards?.map((c) => <CardRow key={c.ref} card={c} selected={c.ref === selected} onSelect={onSelect} />)}
    </div>
  );
}
