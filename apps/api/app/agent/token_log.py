"""Token cua tung luot chat, doc tu `usageMetadata` cua chinh response.

Khac han o chi phi thang trong usage.py: so ben do la metric Cloud
Monitoring cua CA PROJECT — khong mang nhan nao cua ung dung nen khong
tach duoc theo phien hay theo nguoi hoi, va con tre 1-2 phut. Vertex AI
thi tra `usageMetadata` ngay trong response cua tung lenh goi, dung den
tung token va co ngay lap tuc. Hai duong nay bo sung cho nhau chu khong
thay the: bang nay chi dem phan AI Agent goi, con so thang van la cai duy
nhat bao gom moi lenh goi Vertex AI trong project.

Mot luot chat goi Vertex AI HAI duong: ADK Runner (service.py) va
`generate_content` trong sql_gen.py khi agent dich cau hoi sang WHERE.
Duong thu hai nam sau nhieu lop cua ADK — khong tiem session_id xuong toi
do duoc — nen module dung ContextVar: service.py mo mot "so tam" cho ca
luot, ca hai duong cong vao do, het luot ghi xuong DB mot lan.

NGUYEN TAC: ghi token KHONG duoc lam hong cuoc chat. `save()` nuot moi
loi — mat mot dong thong ke con hon mat cau tra loi da ton tien roi.
"""

from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from ..db import db
from .usage import PRICE_PER_TOKEN, cost_of

# model -> [input_tokens, output_tokens] cua luot dang chay. None = dang
# goi ngoai mot luot chat (test, job nen) — luc do add() im lang bo qua
# thay vi dung, de khong ai phai nho mo context truoc khi goi Vertex AI.
_turn: ContextVar[dict[str, list[int]] | None] = ContextVar("agent_token_turn", default=None)


@contextmanager
def collecting() -> Iterator[dict[str, list[int]]]:
    """Mo so tam cho mot luot chat. Tra ve chinh dict do de goi save()."""
    bucket: dict[str, list[int]] = {}
    token = _turn.set(bucket)
    try:
        yield bucket
    finally:
        _turn.reset(token)


def add(model: str, input_tokens: int, output_tokens: int) -> None:
    bucket = _turn.get()
    if bucket is None:
        return
    row = bucket.setdefault(model, [0, 0])
    row[0] += max(0, input_tokens)
    row[1] += max(0, output_tokens)


def add_response(model: str, usage: object | None) -> None:
    """Cong `usageMetadata` cua mot response vao so tam.

    Token "suy nghi" (thinking) duoc gop vao OUTPUT chu khong bo qua:
    Google tinh tien chung nhu token ra, bo di thi so tien hien ra thap
    hon hoa don that.
    """
    if usage is None:
        return
    out = (getattr(usage, "candidates_token_count", 0) or 0) \
        + (getattr(usage, "thoughts_token_count", 0) or 0)
    add(model, getattr(usage, "prompt_token_count", 0) or 0, out)


def save(session_id: str, user_email: str, bucket: dict[str, list[int]]) -> None:
    """Ghi so tam xuong DB. Khong bao gio nem exception (xem docstring module)."""
    if not bucket:
        return
    rows = [(session_id, user_email, model, inp, out)
            for model, (inp, out) in sorted(bucket.items()) if inp or out]
    if not rows:
        return
    try:
        with db() as conn, conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO agent_token_usage"
                " (session_id, user_email, model, input_tokens, output_tokens)"
                " VALUES (%s, %s, %s, %s, %s)",
                rows,
            )
    except Exception:  # noqa: BLE001
        # DB loi thi luot chat van phai tra ve duoc cau tra loi. Hau qua
        # duy nhat la con so cua phien thieu di luot nay.
        pass


def session_usage(session_id: str, user_email: str) -> dict:
    """Token + uoc tinh chi phi cua RIENG mot phien chat.

    Loc ca `user_email`: dan session_id cua nguoi khac vao URL chi ra bang
    rong chu khong lo hoi thoai hay chi phi cua ho.

    Tien tinh y het o chi phi thang — cung PRICE_PER_TOKEN, cung cach bo
    trong model chua co gia thay vi cong thieu mot cach im lang.
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT model,"
            "       SUM(input_tokens)::bigint  AS input_tokens,"
            "       SUM(output_tokens)::bigint AS output_tokens,"
            "       MAX(created_at)            AS last_at"
            "  FROM agent_token_usage"
            " WHERE session_id = %s AND user_email = %s"
            " GROUP BY model ORDER BY model",
            (session_id, user_email),
        )
        rows = cur.fetchall()

    by_model: list[dict] = []
    unpriced: list[str] = []
    last_at = None
    for r in rows:
        inp, out = int(r["input_tokens"] or 0), int(r["output_tokens"] or 0)
        cost = cost_of(r["model"], inp, out)
        if cost is None and r["model"] not in PRICE_PER_TOKEN:
            unpriced.append(r["model"])
        by_model.append({"model": r["model"], "input_tokens": inp,
                         "output_tokens": out, "cost_usd": cost})
        if r["last_at"] and (last_at is None or r["last_at"] > last_at):
            last_at = r["last_at"]

    return {
        "session_id": session_id,
        "input_tokens": sum(r["input_tokens"] for r in by_model),
        "output_tokens": sum(r["output_tokens"] for r in by_model),
        "total_tokens": sum(r["input_tokens"] + r["output_tokens"] for r in by_model),
        "cost_usd": sum(r["cost_usd"] or 0.0 for r in by_model),
        "unpriced_models": sorted(unpriced),
        "by_model": by_model,
        # Doi ve UTC truoc khi dinh dang: connection co the dang o mui gio
        # khac, va man hinh doc chuoi nay nhu gio UTC.
        "last_at": (last_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if last_at else None),
    }
