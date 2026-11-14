const STYLE: Record<string, string> = {
  wait: "border-wait border-dashed",
  prog: "border-walter bg-[conic-gradient(#01B7FF_0_50%,transparent_0)]",
  late: "border-late",
  done: "border-ok bg-ok",
  idle: "border-muted",
};

export function StatusDot({ kind }: { kind: string }) {
  return <i aria-hidden className={`inline-block h-[13px] w-[13px] shrink-0 rounded-full border-2 ${STYLE[kind] ?? STYLE.idle}`} />;
}
