"""`walter-devboard status`: what the board is waiting on — the model pause, failed reads, sessions left to read."""
from __future__ import annotations


def report(conn) -> dict:
    pause = conn.execute("select value from devboard.state where key = 'pause'").fetchone()
    pause = pause["value"] if pause else None
    readings = {r["status"]: r["n"] for r in conn.execute(
        "select status, count(*) n from devboard.readings group by status order by status").fetchall()}
    failed = conn.execute("""select kind, source_ref, from_seq, to_seq, attempts, error, at from devboard.readings
                             where status = 'failed' order by at desc limit 10""").fetchall()
    s = conn.execute("""select count(*) filter (where eligible) eligible,
                               count(*) filter (where eligible and dirty) to_read from devboard.sessions""").fetchone()
    last = conn.execute("select at from devboard.state where key = 'pause'").fetchone()
    lines = []
    if pause:
        lines.append(f"en pause : quota Claude Pro ou route indisponible (lecture {pause.get('what')}, depuis "
                     f"{pause.get('at')}) — reprend seule au prochain passage")
    else:
        lines.append("lectures actives")
    lines.append(f"{s['to_read']} session(s) à lire sur {s['eligible']} suivies")
    if failed:
        lines.append(f"{readings.get('failed', 0)} lecture(s) en échec, dernière : {failed[0]['source_ref']} "
                     f"({failed[0]['error'] or 'sans détail'})")
    return {"pause": pause, "readings": readings, "failed": failed,
            "sessions": {"eligible": s["eligible"], "to_read": s["to_read"]},
            "last_pass": last["at"] if last else None, "text": "\n".join(lines)}
