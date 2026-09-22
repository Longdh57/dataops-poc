"""AI Agent (Google ADK).

Pham vi duoc kiem THAT o lop queries.py (khong can mock ADK gi ca — day la
diem cot loi phai dung: tool khong duoc thay du lieu ngoai bang cua no).
Phan API/endpoint thi mock `agent.chat()` de khong goi Vertex AI that trong
test — chi kiem plumbing: dang nhap bat buoc, response tra dung session_id.
"""

import psycopg
from psycopg.rows import dict_row

from conftest import ADMIN, TX, as_user

from app import main as main_module
from app.agent import sql_gen
from app.agent.queries import Scope, list_open_tickets, list_qc_exceptions

URL = "postgresql://dataops:dataops@localhost:5432/dataops"


def _cursor():
    conn = psycopg.connect(URL, row_factory=dict_row)
    return conn, conn.cursor()


def test_list_qc_exceptions_khong_lo_pham_vi():
    conn, cur = _cursor()
    try:
        rows = list_qc_exceptions(cur, Scope(unrestricted=False, states=frozenset({"TX"})))
        for row in rows:
            assert row["state"] == "TX"
    finally:
        conn.close()


def test_list_open_tickets_khong_lo_pham_vi():
    conn, cur = _cursor()
    try:
        rows = list_open_tickets(cur, Scope(unrestricted=False, states=frozenset({"TX"})))
        for row in rows:
            assert row["state"] == "TX"
    finally:
        conn.close()


def test_scope_rong_tra_ve_rong_khong_phai_toan_cuc():
    """Vai tro pham vi rong (khong duoc gan bang nao) phai thay danh sach
    rong — KHONG duoc ngam dinh thanh 'xem tat ca', do la loi ro ri nghiem
    trong nhat co the co o tang nay."""
    conn, cur = _cursor()
    try:
        rows = list_qc_exceptions(cur, Scope(unrestricted=False, states=frozenset()))
        assert rows == []
    finally:
        conn.close()


# --------------------------------------- get_fact: sinh WHERE tu ngon ngu

def test_validate_where_chap_nhan_dieu_kien_binh_thuong():
    assert sql_gen._validate_where("state = 'TX' AND deposit > 100000") is None
    assert sql_gen._validate_where("institution ILIKE '%wells fargo%' AND year = 2026") is None
    # Nhom ngoac hop le sau AND/OR/IN khong duoc bi hieu nham la goi ham.
    assert sql_gen._validate_where("state = 'TX' AND (year = 2025 OR year = 2026)") is None
    assert sql_gen._validate_where("state IN ('TX', 'CA')") is None


def test_validate_where_tu_choi_ngoac_khong_can_bang():
    """Day la lo hong that: ngoac le lam dieu kien pham vi ma code AND vao
    bi rot sang nhanh OR sai, nho toan tu AND uu tien cao hon OR."""
    assert sql_gen._validate_where("1=1) OR (state='CA'") is not None


def test_validate_where_tu_choi_nhay_don_khong_can_bang():
    assert sql_gen._validate_where("institution ILIKE '%wells") is not None


def test_validate_where_tu_choi_cham_phay_va_comment():
    assert sql_gen._validate_where("state = 'TX'; DELETE FROM ticket") is not None
    assert sql_gen._validate_where("state = 'TX' -- bo qua phan sau") is not None
    assert sql_gen._validate_where("state = 'TX' /* ghi chu */") is not None


def test_validate_where_tu_choi_goi_ham():
    assert sql_gen._validate_where("pg_sleep(1) > 0") is not None
    assert sql_gen._validate_where("count(*) > 0") is not None


def test_validate_where_tu_choi_tu_khoa_cam():
    assert sql_gen._validate_where("1=1 OR (SELECT 1)") is not None
    assert sql_gen._validate_where("1=1 UNION SELECT 1") is not None
    assert sql_gen._validate_where("state ILIKE (information_schema.tables)") is not None


def _cursor_dict():
    conn = psycopg.connect(URL, row_factory=dict_row)
    return conn, conn.cursor()


def test_query_fact_tu_sua_sau_loi_roi_thanh_cong(monkeypatch):
    calls: list[str | None] = []

    def fake_generate(question, reference, prior_error):
        calls.append(prior_error)
        if len(calls) == 1:
            return "1=1) OR (1=1"  # bi validator tu choi (ngoac khong can bang)
        if len(calls) == 2:
            return "cot_khong_ton_tai = 1"  # qua validator, Postgres se bao loi that
        return "state = 'TX'"

    monkeypatch.setattr(sql_gen, "_generate_where", fake_generate)

    conn, cur = _cursor_dict()
    try:
        result = sql_gen.query_fact_natural_language(
            cur, Scope(unrestricted=False, states=frozenset({"TX"})), "cau hoi bat ky")
    finally:
        conn.close()

    assert result["attempts"] == 3
    assert result["sql_where"] == "state = 'TX'"
    assert all(r["state"] == "TX" for r in result["rows"])
    assert calls[1] is not None  # loi validator lan 1 duoc dua vao prompt lan 2
    assert calls[2] is not None  # loi Postgres that lan 2 duoc dua vao prompt lan 3


def test_query_fact_het_luot_van_sai_tra_ve_loi_ro_rang(monkeypatch):
    monkeypatch.setattr(sql_gen, "_generate_where", lambda q, r, e: "1=1) OR (1=1")

    conn, cur = _cursor_dict()
    try:
        result = sql_gen.query_fact_natural_language(
            cur, Scope(unrestricted=False, states=frozenset({"TX"})), "cau hoi bat ky")
    finally:
        conn.close()

    assert result["error"] == "khong_the_truy_van"
    assert result["last_error"]


def test_query_fact_khong_lo_pham_vi_du_dieu_kien_qua_rong(monkeypatch):
    """Model co the "gia vo tot bung" tra ve dieu kien rong (1=1) de xem het
    du lieu — dieu kien pham vi AND o tang SQL + loc lai o Python van phai
    giu dung, bat ke fragment model dua ra la gi."""
    monkeypatch.setattr(sql_gen, "_generate_where", lambda q, r, e: "1=1")

    conn, cur = _cursor_dict()
    try:
        result = sql_gen.query_fact_natural_language(
            cur, Scope(unrestricted=False, states=frozenset({"TX"})), "cho toi xem tat ca")
    finally:
        conn.close()

    assert "rows" in result
    for row in result["rows"]:
        assert row["state"] == "TX"


def test_query_fact_chay_duoc_voi_ilike_dau_phan_tram(monkeypatch):
    """Hoi quy: psycopg doc chuoi SQL nhu template %-format khi co truyen
    params, nen dau % that trong ILIKE '%...%' (cach loc ten to chuc DUY
    NHAT duoc huong dan trong prompt) phai duoc gap doi (%%) truoc khi ghep
    vao cau lenh, neu khong se loi 'only %s/%b/%t are allowed'."""
    monkeypatch.setattr(
        sql_gen, "_generate_where", lambda q, r, e: "institution ILIKE '%wells%'")

    conn, cur = _cursor_dict()
    try:
        result = sql_gen.query_fact_natural_language(
            cur, Scope(unrestricted=False, states=frozenset({"TX"})), "to chuc co chu wells")
    finally:
        conn.close()

    assert "rows" in result, f"khong duoc loi: {result}"
    assert result["attempts"] == 1


def test_agent_chat_goi_dung_service_va_tra_ve_session_id(client, monkeypatch):
    captured = {}

    async def fake_chat(p, message, session_id):
        captured["email"] = p.email
        captured["message"] = message
        captured["session_id"] = session_id
        return "cau tra loi gia lap", "session-abc"

    monkeypatch.setattr(main_module.agent, "chat", fake_chat)

    res = client.post("/api/agent/chat", json={"message": "tinh hinh sao roi?"},
                      headers=as_user(TX))
    assert res.status_code == 200
    body = res.json()
    assert body["reply"] == "cau tra loi gia lap"
    assert body["session_id"] == "session-abc"
    assert captured["email"] == TX
    assert captured["session_id"] is None


def test_agent_chat_gui_lai_session_id_de_noi_tiep(client, monkeypatch):
    async def fake_chat(p, message, session_id):
        return f"echo:{session_id}", session_id or "moi"

    monkeypatch.setattr(main_module.agent, "chat", fake_chat)

    res = client.post("/api/agent/chat",
                      json={"message": "tiep tuc", "session_id": "session-abc"},
                      headers=as_user(TX))
    assert res.status_code == 200
    assert res.json()["reply"] == "echo:session-abc"


def test_agent_chat_bat_buoc_co_message(client):
    res = client.post("/api/agent/chat", json={"message": ""}, headers=as_user(ADMIN))
    assert res.status_code == 422


def test_agent_chat_bat_buoc_dang_nhap(client):
    res = client.post("/api/agent/chat", json={"message": "hi"})
    assert res.status_code == 401
