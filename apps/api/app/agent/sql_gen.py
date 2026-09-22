"""NL -> SQL cho get_fact: model chi sinh MOT dieu kien WHERE, khong phai
ca cau lenh — xem Context trong ke hoach da duyet cho ly do.

Bon vong kiem tra truoc khi mot dieu kien duoc phep chay (`_validate_where`):
  1. Ngoac () va nhay don ' can bang — dong dung dieu lo hong "1=1) OR (..."
     pha vo nhom bao ngoai ma code tu ghep, khien dieu kien pham vi bi AND
     vao nhanh sai (uu tien toan tu AND cao hon OR).
  2. Khong ';', '--', '/*'  — khong noi lenh, khong meo comment.
  3. Khong duoc "goi ham": mot tu ngay truoc dau "(" ma khong phai
     AND/OR/NOT/IN thi bi coi la goi ham va chan (pg_sleep(), count(),...).
     Nhom ngoac binh thuong sau AND/OR/NOT/IN van hop le.
  4. Danh sach tu khoa cam (SELECT/INSERT/.../pg_*/information_schema).

Dieu kien qua duoc bon vong nay van LUON bi AND them dieu kien pham vi o
tang SQL (dung `_scope_where` — ham dang dung cho moi truy van khac trong
queries.py), roi loc lai lan nua o Python sau khi doc — hai lop phong thu,
khong lop nao mot minh la du.
"""

from __future__ import annotations

import re

from fastapi import HTTPException
from google import genai
from google.genai import types

from ..settings import settings
from .queries import Scope, _scope_where

MAX_ATTEMPTS = 3
STATEMENT_TIMEOUT_MS = 3000

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(select|insert|update|delete|drop|alter|truncate|create|grant|revoke|"
    r"copy|call|execute|merge|union|pg_\w*|information_schema)\b",
    re.IGNORECASE,
)
# Mot "tu ngay truoc dau (" ma KHONG phai AND/OR/NOT/IN thi coi la goi ham
# (pg_sleep(...), count(...), v.v.) — phai chan. Nhom ngoac binh thuong sau
# AND/OR/NOT/IN (vi du "... AND (year = 2025 OR year = 2026)") thi hop le.
_CALL_LIKE = re.compile(r"(\w+)\s*\(")
_SAFE_BEFORE_PAREN = {"and", "or", "not", "in"}

_ALLOWED_COLUMNS = (
    "year (int), state (text, ma 2 ky tu), institution_id (int), "
    "institution (text — TEN TO CHUC, cach viet hoa/thuong KHONG on dinh "
    "giua cac nam nen LUON dung ILIKE '%...%' de loc, khong bao gio dung "
    "'='), deposit (bigint, don vi nghin USD), deposit_share (float, 0..1), "
    "prev_deposit (bigint), prev_year (int)"
)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True, project=settings.gcp_project_id, location=settings.region)
    return _client


def _reference_values(cur) -> dict:
    """Gia tri that dang co trong fact_current — truy van song moi lan goi,
    khong cache/ghi file, nen khong bao gio lech sau mot lan sync moi."""
    cur.execute("SELECT DISTINCT state FROM fact_current ORDER BY state")
    states = [r["state"] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT year FROM fact_current ORDER BY year")
    years = [r["year"] for r in cur.fetchall()]
    return {"states": states, "years": years}


def _parens_valid(fragment: str) -> bool:
    """Dem tong so KHONG du — "1=1) OR (state='CA'" co dung 1 dau ( va 1
    dau ), nhung dong TRUOC khi mo: dung tach nhom bao ngoai ma code tu
    ghep, roi dieu kien pham vi bi AND vao nhanh sai (uu tien AND cao hon
    OR). Phai theo doi do sau thuc su, tu choi ngay khi do sau am."""
    depth = 0
    for ch in fragment:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _validate_where(fragment: str) -> str | None:
    """Tra ve thong bao loi neu dieu kien khong an toan, None neu qua duoc."""
    if not fragment or not fragment.strip():
        return "dieu kien rong"
    if not _parens_valid(fragment):
        return "ngoac tron () khong can bang hoac sai thu tu"
    if fragment.count("'") % 2 != 0:
        return "dau nhay don ' khong can bang"
    if ";" in fragment or "--" in fragment or "/*" in fragment:
        return "khong duoc chua ';', '--', hoac '/*'"
    for m in _CALL_LIKE.finditer(fragment):
        if m.group(1).lower() not in _SAFE_BEFORE_PAREN:
            return "khong duoc goi ham (chi dung toan tu so sanh/logic don gian)"
    if _FORBIDDEN_KEYWORDS.search(fragment):
        return "chua tu khoa khong duoc phep (chi la mot dieu kien loc, khong phai cau lenh)"
    return None


def _generate_where(question: str, reference: dict, prior_error: str | None) -> str:
    retry_note = f"\n\nLan truoc bi tu choi vi: {prior_error}. Sua lai cho dung." if prior_error else ""
    prompt = f"""Dich cau hoi sau thanh MOT DIEU KIEN loc (WHERE) tren bang fact_current.

Cot dung duoc: {_ALLOWED_COLUMNS}

Bang hien co state: {reference['states']}
Bang hien co year: {reference['years']}

CHI tra ve DUY NHAT bieu thuc dieu kien — KHONG co chu 'WHERE', KHONG co
'SELECT', KHONG co dau cham phay, KHONG giai thich gi them, KHONG dung
markdown/code fence. Vi du dung dinh dang:
  state = 'TX' AND deposit > 100000
  institution ILIKE '%wells fargo%' AND year = 2026
{retry_note}

Cau hoi: {question}"""

    resp = _get_client().models.generate_content(
        model=settings.agent_model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0),
    )
    text = (resp.text or "").strip()
    # Phong khi model van "ro" markdown code fence du da can:
    text = re.sub(r"^```(sql)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    return text.rstrip(";").strip()


def query_fact_natural_language(cur, scope: Scope, question: str, limit: int = 50) -> dict:
    """Sinh dieu kien WHERE tu cau hoi tu nhien, thu chay toi da MAX_ATTEMPTS
    lan — loi lan truoc (validator hoac chinh Postgres bao) duoc dua lai vao
    lan sinh ke tiep de model tu sua. Het luot ma van sai thi tra ve loi ro
    rang thay vi bia du lieu.
    """
    reference = _reference_values(cur)
    scope_sql, scope_params = _scope_where(scope)

    last_error: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            fragment = _generate_where(question, reference, last_error)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"khong goi duoc Vertex AI de sinh SQL: {exc}") from exc

        problem = _validate_where(fragment)
        if problem:
            last_error = f"dieu kien '{fragment}' bi tu choi: {problem}"
            continue

        # psycopg doc ca chuoi SQL nhu template kieu %-format khi co truyen
        # params, nen dau % that trong dieu kien (bat buoc co voi ILIKE
        # '%...%') phai duoc gap doi thanh %% de khong bi hieu nham thanh
        # placeholder — khong lam vay se loi "only %s/%b/%t are allowed".
        where_clause = f"({fragment.replace('%', '%%')})"
        params = []
        if scope_sql:
            where_clause += f" AND {scope_sql}"
            params = list(scope_params)

        sql = (
            "SELECT year, state, institution_id, institution, deposit, deposit_share, "
            f"prev_deposit, prev_year FROM fact_current WHERE {where_clause} LIMIT %s"
        )
        try:
            cur.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
            cur.execute(sql, [*params, limit])
            rows = cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            # Postgres huy ca transaction sau 1 loi — khong rollback thi lan
            # thu tiep theo tren CUNG connection se loi day chuyen voi
            # "current transaction is aborted", che mat loi that cua fragment.
            cur.connection.rollback()
            continue

        # Loc lai o Python — phong thu them, du dieu kien pham vi da AND o SQL.
        if not scope.unrestricted:
            rows = [r for r in rows if r["state"] in scope.states]
        return {"sql_where": fragment, "rows": rows[:limit], "attempts": attempt}

    return {
        "error": "khong_the_truy_van",
        "message": "Khong the truy van tren du lieu goc hien co sau "
                   f"{MAX_ATTEMPTS} lan thu.",
        "last_error": last_error,
    }
