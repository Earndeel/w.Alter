"""One-shot CLI for the out-of-process Lot 2.1 shadow spool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptive_operator.observation import ObservationDetail
from adaptive_operator.shadow_spool import ShadowSpool


def exit_code_for(result) -> int:
    """Fail the sidecar process only when replay cannot make progress."""
    return 2 if any(
        str(error).startswith("unpaired_result:")
        for error in result.replay_errors
    ) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device-id", default="configured-mac")
    parser.add_argument(
        "--detail",
        choices=[item.value for item in ObservationDetail if item is not ObservationDetail.PIXELS],
        default=ObservationDetail.RELEVANT.value,
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    result = ShadowSpool(
        database=args.state_db,
        device_id=args.device_id,
        output_dir=args.output,
        detail=ObservationDetail(args.detail),
        batch_size=args.batch_size,
    ).poll_once()
    print(json.dumps(result.__dict__, ensure_ascii=False, default=list, sort_keys=True))
    return exit_code_for(result)


if __name__ == "__main__":
    raise SystemExit(main())
