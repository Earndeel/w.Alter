"""Durable, idempotent spool for the out-of-process V2 shadow sidecar."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from adaptive_operator.observation import ObservationDetail
from adaptive_operator.shadow_sidecar import ShadowSidecar


@dataclass(frozen=True)
class ShadowSpoolResult:
    records_seen: int
    records_created: int
    next_cursor: int
    additional_backend_calls: int
    failures_affecting_v1: int
    replay_errors: tuple[str, ...]


class ShadowSpool:
    def __init__(
        self,
        *,
        database: str | Path,
        device_id: str,
        output_dir: str | Path,
        detail: ObservationDetail = ObservationDetail.RELEVANT,
        max_elements: int = 20,
        batch_size: int = 100,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.events_dir = self.output_dir / "events"
        self.cursor_path = self.output_dir / "cursor.json"
        self.sidecar = ShadowSidecar(
            database=database,
            device_id=device_id,
            detail=detail,
            max_elements=max_elements,
            batch_size=batch_size,
        )

    def poll_once(self, *, cursor: int | None = None) -> ShadowSpoolResult:
        current = self._cursor() if cursor is None else cursor
        result = self.sidecar.poll_once(cursor=current)
        self.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.output_dir.chmod(0o700)
        self.events_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.events_dir.chmod(0o700)
        for existing in self.events_dir.glob("*.json"):
            existing.chmod(0o600)
        created = 0
        for record in result.records:
            path = self.events_dir / f"{record.result_message_id:012d}.json"
            try:
                with path.open("x", encoding="utf-8") as handle:
                    json.dump(asdict(record), handle, ensure_ascii=False, sort_keys=True)
                    handle.write("\n")
                path.chmod(0o600)
                created += 1
            except FileExistsError:
                pass
        self._write_cursor(result.next_cursor)
        return ShadowSpoolResult(
            records_seen=len(result.records),
            records_created=created,
            next_cursor=result.next_cursor,
            additional_backend_calls=result.additional_backend_calls,
            failures_affecting_v1=result.failures_affecting_v1,
            replay_errors=result.replay_errors,
        )

    def _cursor(self) -> int:
        if not self.cursor_path.exists():
            return 0
        raw = json.loads(self.cursor_path.read_text(encoding="utf-8"))
        cursor = int(raw.get("cursor", 0))
        if cursor < 0:
            raise ValueError("shadow cursor cannot be negative")
        return cursor

    def _write_cursor(self, cursor: int) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.cursor_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps({"cursor": cursor}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.cursor_path)
        self.cursor_path.chmod(0o600)
