"""Token + chi phi Vertex AI thang nay — DOC TU Cloud Monitoring, khong tu dem.

GCP da dem san token o metric
`aiplatform.googleapis.com/publisher/online_serving/token_count`, nen ung
dung khong phai cong don `usage_metadata` cua tung request. Doi lai, con
so o day co hai gioi han phai noi ro voi nguoi doc, khong duoc giau:

1. La CUA CA PROJECT. No gop ca hai duong goi Vertex AI — ADK Runner
   trong service.py va `generate_content` truc tiep trong sql_gen.py — va
   KHONG tach duoc theo nguoi hoi hay theo phien, vi metric khong mang
   nhan nao cua ung dung. Muon so theo tung phien chat thi doc
   token_log.py — cho do ghi `usageMetadata` cua tung lenh goi.
2. Tien la UOC TINH: token nhan don gia niem yet. Khong tru credit, cam
   ket chi tieu hay giam gia hop dong. Dung de canh chung "dang ton bao
   nhieu", KHONG dung de doi soat — so that nam o Cloud Billing.

Metric con tre vai phut so voi thoi diem goi that, nen cau hoi vua hoi
xong chua chac da nam trong con so.
"""

from __future__ import annotations

import datetime as dt
import threading
import urllib.parse

from ..settings import settings

METRIC = "aiplatform.googleapis.com/publisher/online_serving/token_count"

# USD cho MOT token. Doi chieu bang Cloud Billing Catalog API — service
# Vertex AI la services/C7E2-9256-1C43:
#   GET https://cloudbilling.googleapis.com/v1/services/C7E2-9256-1C43/skus
# Lay SKU ban "GA ... - Predictions" (khong phai Batch/Priority/preview):
#   "Gemini 2.5 Flash GA Text Input - Predictions"            = 3.0e-07
#   "Gemini 2.5 Flash GA Thinking Text Output - Predictions"  = 2.5e-06
# Model khong co trong bang van hien token, chi bo trong phan tien — tha
# de trong con hon hien mot con so bia.
#
# LUU Y ve gemini-2.5-pro: tren 200K token context Google tinh gia cao hon
# ($2.50/$15 thay vi $1.25/$10). Bang nay lay bac thap, nen neu doi sang
# Pro thi con so se THAP hon thuc te.
PRICE_PER_TOKEN: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.30e-6, "output": 2.50e-6},
    "gemini-2.5-flash-lite": {"input": 0.10e-6, "output": 0.40e-6},
    "gemini-2.5-pro": {"input": 1.25e-6, "output": 10.0e-6},
}

# Metric tre vai phut va man hinh Agent goi lai moi lan mo, nen cache de
# khong ban Monitoring API moi luot chat. Cache theo tung instance Cloud
# Run — chap nhan duoc, vi day la so uoc tinh chu khong phai so ky.
_CACHE_TTL = dt.timedelta(minutes=5)
_lock = threading.Lock()
_cache: tuple[dt.datetime, dict] | None = None


def cost_of(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """USD uoc tinh theo gia niem yet. None = model chua co trong bang gia.

    Dung chung voi token_log.py (so theo phien chat) de hai man hinh khong
    bao gio lech nhau vi hai cong thuc khac nhau.
    """
    price = PRICE_PER_TOKEN.get(model)
    if price is None:
        return None
    return input_tokens * price["input"] + output_tokens * price["output"]


def _month_start(now: dt.datetime) -> dt.datetime:
    """Dau thang theo UTC.

    Co y dung UTC chu khong phai gio Viet Nam: Monitoring API lam viec
    bang UTC, va lay them mot moc gio dia phuong chi de lech mot cach
    khac voi Cloud Billing (von chot theo mui gio cua tai khoan thanh
    toan). Lech chi nam trong vai gio dau thang.
    """
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _fetch(start: dt.datetime, end: dt.datetime) -> list[dict]:
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    params = [
        ("filter", f'metric.type="{METRIC}"'),
        ("interval.startTime", start.strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("interval.endTime", end.strftime("%Y-%m-%dT%H:%M:%SZ")),
        # Gom theo ngay roi tu cong — mot alignmentPeriod bang ca thang se
        # cham tran so diem Monitoring tra ve khi cua so dai.
        ("aggregation.alignmentPeriod", "86400s"),
        ("aggregation.perSeriesAligner", "ALIGN_SUM"),
        ("aggregation.crossSeriesReducer", "REDUCE_SUM"),
        ("aggregation.groupByFields", "metric.label.type"),
        ("aggregation.groupByFields", "resource.label.model_user_id"),
    ]
    url = (f"https://monitoring.googleapis.com/v3/projects/{settings.gcp_project_id}"
           f"/timeSeries?{urllib.parse.urlencode(params)}")

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    res = AuthorizedSession(creds).get(url, timeout=20)
    if res.status_code >= 300:
        raise RuntimeError(f"Monitoring API {res.status_code}: {res.text[:200]}")
    return res.json().get("timeSeries", [])


def _summarize(series: list[dict], start: dt.datetime, now: dt.datetime) -> dict:
    by_model: dict[str, dict] = {}
    for ts in series:
        model = ts.get("resource", {}).get("labels", {}).get("model_user_id", "?")
        kind = ts.get("metric", {}).get("labels", {}).get("type", "?")
        if kind not in ("input", "output"):
            continue
        n = sum(int(p["value"]["int64Value"]) for p in ts.get("points", []))
        row = by_model.setdefault(
            model, {"model": model, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
        row[f"{kind}_tokens"] += n

    unpriced: list[str] = []
    for model, row in by_model.items():
        row["cost_usd"] = cost_of(model, row["input_tokens"], row["output_tokens"])
        if row["cost_usd"] is None:
            unpriced.append(model)

    rows = sorted(by_model.values(), key=lambda r: r["model"])
    return {
        "available": True,
        "period_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_tokens": sum(r["input_tokens"] for r in rows),
        "output_tokens": sum(r["output_tokens"] for r in rows),
        "total_tokens": sum(r["input_tokens"] + r["output_tokens"] for r in rows),
        "cost_usd": sum(r["cost_usd"] or 0.0 for r in rows),
        # Model chua co trong PRICE_PER_TOKEN: tien cua chung KHONG nam
        # trong cost_usd o tren. Man hinh phai noi ro thay vi lang le
        # cong thieu.
        "unpriced_models": sorted(unpriced),
        "by_model": rows,
    }


def month_usage(force: bool = False) -> dict:
    """Token + uoc tinh chi phi Vertex AI tu dau thang (UTC) den bay gio.

    KHONG NEM EXCEPTION — man hinh AI Agent goi ham nay chi de hien mot o
    phu; thieu quyen monitoring.viewer, chua cau hinh project, hay
    Monitoring API tra loi deu khong duoc lam hong cho chat. Loi tra ve
    duoi dang {"available": False, "reason": ...} de man hinh im lang bo
    qua, giong cach trigger_job() tra ve (False, ly_do).
    """
    global _cache

    if not settings.gcp_project_id:
        return {"available": False, "reason": "chua cau hinh GCP_PROJECT_ID"}

    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    with _lock:
        if not force and _cache and now - _cache[0] < _CACHE_TTL:
            return _cache[1]

    start = _month_start(now)
    try:
        out = _summarize(_fetch(start, now), start, now)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"khong doc duoc Cloud Monitoring: {exc}"}

    with _lock:
        _cache = (now, out)
    return out
