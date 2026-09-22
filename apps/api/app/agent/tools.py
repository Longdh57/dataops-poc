"""ADK tool wrappers.

Tat ca la SELECT — khong tool nao ghi/sua duoc gi (dung nguyen tac "AI Agent
chi doc" cua docs/quy-trinh-chat-luong.md). Pham vi lay tu
`tool_context.state`, do server gan luc mo session trong service.py — LLM
khong bao gio truyen hay doi duoc gia tri nay, du co the "gia vo" goi tool
voi tham so scope trong cau hoi.
"""

from google.adk.tools import ToolContext

from ..db import db
from . import queries
from .queries import Scope
from .sql_gen import query_fact_natural_language


def _scope_from(tool_context: ToolContext) -> Scope:
    st = tool_context.state
    return Scope(
        unrestricted=bool(st.get("unrestricted")),
        states=frozenset(st.get("scope_states") or []),
    )


def list_qc_exceptions(tool_context: ToolContext, severity: str | None = None,
                       rule_id: str | None = None, year: int | None = None) -> list[dict]:
    """Liet ke vi pham QC (qc_exception) cua lan nap hien tai, trong pham vi cua nguoi hoi.

    Dung khi can xem chi tiet tung vi pham cu the — ten luat, khoa (bang/to
    chuc/nam), va so lieu quan sat duoc (observed). Loc duoc theo severity
    (critical/warning), rule_id, hoac year neu nguoi hoi chi ro.
    """
    scope = _scope_from(tool_context)
    with db() as conn, conn.cursor() as cur:
        return queries.list_qc_exceptions(cur, scope, severity=severity, rule_id=rule_id, year=year)


def summarize_qc_exceptions(tool_context: ToolContext) -> dict:
    """Tom tat vi pham QC cua lan nap hien tai theo tung luat va muc do, trong pham vi.

    Goi dau tien khi nguoi hoi can "tinh hinh chung" — tra ve tong so va so
    luong theo tung rule_id, khong liet ke tung dong nen re token hon nhieu
    so voi list_qc_exceptions.
    """
    scope = _scope_from(tool_context)
    with db() as conn, conn.cursor() as cur:
        return queries.summarize_qc_exceptions(cur, scope)


def list_open_tickets(tool_context: ToolContext, state: str | None = None) -> list[dict]:
    """Liet ke ticket dang mo (open hoac awaiting_verify), trong pham vi.

    Ticket la loi da duoc XAC NHAN bang bang chung — khac vi pham QC (chi la
    nghi ngo cua may). Dung khi nguoi hoi can biet cai gi dang chan phat
    hanh, hoac hoi ve bang chung (evidence) cua mot loi da bao.
    """
    scope = _scope_from(tool_context)
    with db() as conn, conn.cursor() as cur:
        return queries.list_open_tickets(cur, scope, state=state)


def get_fact(tool_context: ToolContext, question: str) -> dict:
    """Tra cuu du lieu goc trong fact_current bang cau hoi tu do (khong biet
    truoc khoa chinh xac) — vi du: theo ten to chuc, theo khoang deposit,
    theo nam/bang, hoac ket hop nhieu dieu kien.

    Dung khi cac tool khac khong du: list_qc_exceptions/list_open_tickets
    chi tra vi pham/ticket, khong tra duoc du lieu goc theo dieu kien tu do.
    Tool nay tu sinh dieu kien loc, thu toi da 3 lan (tu sua neu lan truoc
    sai), roi tra ve {"error": "khong_the_truy_van", ...} neu van khong
    duoc — luc do phai noi that voi nguoi dung la khong tra loi duoc, KHONG
    duoc bia so lieu.
    """
    scope = _scope_from(tool_context)
    with db() as conn, conn.cursor() as cur:
        return query_fact_natural_language(cur, scope, question)
