"""AI Agent (Gemini qua Vertex AI) — doc Issue Log va tra loi, khong quyet dinh.

Dung mo hinh "RAG-lite": khong co vector DB, moi lan hoi la mot lan doc
lai vi pham QC (qc_exception) + ticket (bang chung nam san o cot
`evidence`) trong PHAM VI cua nguoi hoi, nhet thang vao prompt. Agent chi
la lop DOC THEM tren Deterministic QC Engine da co — no khong tu dong ket
luan cho qua, dong ticket, hay sua so. Ba dieu do van chi lam duoc qua
`POST /api/release` va co che doi chieu cua QC Runner (xem
docs/quy-trinh-chat-luong.md).
"""

import json
from typing import Any

from fastapi import HTTPException
from google import genai
from google.genai import types

from .authz import Principal, scope_clause
from .settings import settings

SYSTEM_PROMPT = """\
Ban la tro ly review chat luong du lieu cho he thong Data Operations.

Ban CHI duoc tra loi dua tren du lieu trong phan "Ngu canh" duoc cung cap
o moi luot hoi — do la vi pham QC (qc_exception) va ticket dang mo, DA
duoc loc dung theo pham vi cua nguoi hoi. Khong dung kien thuc ngoai,
khong doan so lieu khong co trong ngu canh.

Neu ngu canh khong co du thong tin de tra loi (vi du: hoi ve mot ma vi
pham hoac ticket khong xuat hien trong danh sach), phai noi ro "khong du
can cu trong du lieu hien co" thay vi doan.

Ban CO THE: tom tat tinh hinh chung, giai thich mot vi pham cu the bang
ngon ngu tu nhien, va xep hang muc do uu tien xu ly kem ly do.

Ban KHONG DUOC:
- Coi mot ticket la da dong hay da xac minh — CHI QC Runner moi dong duoc
  ticket, bang cach doi so thuc te voi expected_value o lan nap ke tiep.
- Noi thay quyet dinh ky/duyet — CHI team_lead ky Phieu duyet moi cho phep
  phat hanh du con vi pham.
- De xuat sua so lieu tai dashboard — so sai luon phai quay ve BigQuery
  qua ticket, ung dung nay khong sua so o bat ky dau.

Moi quyet dinh cuoi cung la cua con nguoi. Ban chi ho tro doc va giai
thich co bang chung."""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gcp_project_id:
            raise HTTPException(
                503, "GCP_PROJECT_ID chua cau hinh — AI Agent khong goi duoc Vertex AI")
        _client = genai.Client(
            vertexai=True, project=settings.gcp_project_id, location=settings.region)
    return _client


def build_context(cur, p: Principal, run_id: str | None = None) -> dict[str, Any]:
    """Anh chup vi pham + ticket trong pham vi nguoi hoi, lam ngu canh cho agent.

    Dung lai cung mot logic pham vi voi /api/exceptions va /api/tickets —
    agent khong duoc thay du lieu ngoai pham vi cua nguoi dang chat.
    """
    cur.execute("SELECT qc_run_id, last_run_id FROM sync_state WHERE id = 1")
    st = cur.fetchone() or {}
    target = run_id or st.get("qc_run_id") or st.get("last_run_id")
    if not target:
        return {"run_id": None, "pham_vi": "tat ca" if p.unrestricted else sorted(p.scope_states),
                "by_rule": [], "violation_examples": [], "tickets": [],
                "note": "chua co lan nap nao duoc QC kiem"}

    scope_sql, scope_params = scope_clause(p, None)

    exc_where = ["run_id = %s"]
    exc_params: list = [target]
    if scope_sql:
        exc_where.append(scope_sql)
        exc_params += list(scope_params)
    exc_clause = " AND ".join(exc_where)

    cur.execute(
        f"""SELECT rule_id, severity, count(*) AS n FROM qc_exception
            WHERE {exc_clause} GROUP BY rule_id, severity ORDER BY n DESC""",
        exc_params)
    by_rule = cur.fetchall()

    # Chi lay mot so vi du cu the — day du prompt bang toan bo vi pham
    # (co the hang tram nghin dong) vua ton token vua khong can thiet cho
    # cac cau hoi kieu "giai thich issue nay", "uu tien cai gi truoc".
    cur.execute(
        f"""SELECT id, rule_id, severity, year, state, institution_id, institution, message, observed
            FROM qc_exception WHERE {exc_clause}
            ORDER BY severity, id LIMIT 30""",
        exc_params)
    violation_examples = cur.fetchall()

    tk_where = ["status IN ('open','awaiting_verify')"]
    tk_params: list = []
    if scope_sql:
        tk_where.append(scope_sql)
        tk_params += list(scope_params)
    cur.execute(
        f"""SELECT id, year, state, institution_id, institution, title, expected_value,
                   observed_at_open, last_observed, blocking, status, evidence, from_rule_id
            FROM ticket WHERE {' AND '.join(tk_where)}
            ORDER BY blocking DESC, id LIMIT 30""",
        tk_params)
    tickets = cur.fetchall()

    return {
        "run_id": target,
        "pham_vi": "tat ca" if p.unrestricted else sorted(p.scope_states),
        "by_rule": by_rule,
        "violation_examples": violation_examples,
        "tickets": tickets,
    }


def ask(message: str, history: list[dict[str, str]], context: dict[str, Any]) -> str:
    """Goi Gemini voi ngu canh + lich su hoi thoai, tra ve cau tra loi text."""
    history_text = "\n".join(f"{t['role']}: {t['text']}" for t in history[-10:]) or "(chua co)"

    prompt = f"""### Ngu canh (Issue Log + ticket, JSON — day du du lieu ban duoc dung)
{json.dumps(context, ensure_ascii=False, default=str)}

### Lich su hoi thoai gan nhat
{history_text}

### Cau hoi moi
{message}"""

    try:
        resp = _get_client().models.generate_content(
            model=settings.agent_model,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=0.2),
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"khong goi duoc Vertex AI: {exc}") from exc

    if not resp.text:
        raise HTTPException(502, "Vertex AI tra ve phan hoi rong")
    return resp.text
