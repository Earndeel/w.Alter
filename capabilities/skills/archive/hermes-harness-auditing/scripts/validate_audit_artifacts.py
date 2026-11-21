#!/usr/bin/env python3
"""Deterministically validate a Hermes global audit report and its artifacts.

Usage:
  python3 validate_audit_artifacts.py \
    --report path/to/report.md \
    --metrics path/to/metrics.json \
    [--archive path/to/superseded-provider-report.md]

The script prints JSON and exits non-zero when validation fails. It never prints
matched secret-shaped values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REQUIRED_HEADINGS = (
    "## 1. Verdict exécutif",
    "## 2. Méthode et niveau de preuve",
    "## 3. Cartographie du flux complet",
    "## 4. Sécurité",
    "## 5. Robustesse et observabilité runtime",
    "## 6. Résultats de validation",
    "## 7. Registre des risques priorisés",
    "## 8. Plan d’action coût-bénéfice",
    "## 9. Annexe",
    "## 10. Annexe",
    "## Conclusion",
)

SECRET_PATTERNS = {
    "openai_style": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "google_api": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "telegram_bot": re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()

    report_bytes = args.report.read_bytes()
    report = report_bytes.decode("utf-8")
    metrics_bytes = args.metrics.read_bytes()

    errors: list[str] = []
    metrics_sha = sha256(metrics_bytes)

    try:
        json.loads(metrics_bytes)
        metrics_json_valid = True
    except (UnicodeDecodeError, json.JSONDecodeError):
        metrics_json_valid = False
        errors.append("metrics JSON is invalid")

    missing_headings = [
        heading
        for heading in REQUIRED_HEADINGS
        if heading not in report
    ]
    if missing_headings:
        errors.append("required report headings are missing")

    secret_counts = {
        name: len(pattern.findall(report))
        for name, pattern in SECRET_PATTERNS.items()
    }
    if any(secret_counts.values()):
        errors.append("report contains secret-shaped values")

    hash_embedded = metrics_sha in report
    if not hash_embedded:
        errors.append("current metrics SHA-256 is not embedded in report")

    archive_banner = None
    if args.archive:
        archive_text = args.archive.read_text(encoding="utf-8")
        archive_banner = archive_text.startswith("# ARCHIVE")
        if not archive_banner:
            errors.append("superseded report is not marked as archive")

    result = {
        "ok": not errors,
        "errors": errors,
        "report": {
            "path": str(args.report),
            "sha256": sha256(report_bytes),
            "bytes": len(report_bytes),
            "lines": len(report.splitlines()),
            "missing_headings": missing_headings,
            "secret_pattern_counts": secret_counts,
        },
        "metrics": {
            "path": str(args.metrics),
            "sha256": metrics_sha,
            "json_valid": metrics_json_valid,
            "hash_embedded": hash_embedded,
        },
        "archive_banner": archive_banner,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
