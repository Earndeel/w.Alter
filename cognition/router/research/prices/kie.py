"""Kie.ai market prices."""
from __future__ import annotations

from datetime import datetime

from walter_router.research.web import fetch_json, now

KIE_URL = "https://api.kie.ai/client/v1/model-pricing/page"


def source_kie() -> tuple[dict, datetime, str]:
    records, page = [], 1
    while True:
        body = fetch_json(KIE_URL, {"pageNum": page, "pageSize": 100, "modelDescription": "", "interfaceType": ""})
        data = body["data"]
        if body.get("code") != 200 or data["current"] != page or not 1 <= data["pages"] <= 100:
            raise ValueError("kie: invalid page")
        records.extend(data["records"])
        if page == data["pages"]:
            break
        page += 1
    if len(records) != data["total"]:
        raise ValueError("kie: incomplete catalogue")
    return {"data": records}, now(), KIE_URL
