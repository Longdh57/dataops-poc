"""AI Agent (Google ADK).

Pham vi duoc kiem THAT o lop queries.py (khong can mock ADK gi ca — day la
diem cot loi phai dung: tool khong duoc thay du lieu ngoai bang cua no).
Phan API/endpoint thi mock `agent.chat()` de khong goi Vertex AI that trong
test — chi kiem plumbing: dang nhap bat buoc, response tra dung session_id.
"""

import uuid

import psycopg
from psycopg.rows import dict_row

from conftest import ADMIN, TX, as_user

from app import main as main_module
from app.db import db
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

    assert result["error"] == "cannot_query"
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


# ------------------------------- chi phi Vertex AI thang nay (Cloud Monitoring)

def _series(model: str, kind: str, *values: int) -> dict:
    return {
        "resource": {"labels": {"model_user_id": model}},
        "metric": {"labels": {"type": kind}},
        "points": [{"value": {"int64Value": str(v)}} for v in values],
    }


def test_summarize_cong_token_theo_ngay_va_quy_ra_tien():
    """Monitoring tra ve mot diem MOI NGAY (alignmentPeriod 86400s), nen
    tong thang la tong cac diem — khong phai diem cuoi cung."""
    import datetime as dt

    from app.agent import usage

    start = dt.datetime(2026, 9, 1)
    now = dt.datetime(2026, 9, 24)
    out = usage._summarize(
        [_series("gemini-2.5-flash", "input", 1_000_000, 294_664),
         _series("gemini-2.5-flash", "output", 80_000, 4_845)],
        start, now)

    assert out["available"] is True
    assert out["input_tokens"] == 1_294_664
    assert out["output_tokens"] == 84_845
    assert out["total_tokens"] == 1_379_509
    # 1.294664M x $0.30 + 0.084845M x $2.50
    assert round(out["cost_usd"], 4) == round(0.3883992 + 0.2121125, 4)
    assert out["unpriced_models"] == []


def test_summarize_model_chua_co_gia_thi_bao_ra_chu_khong_cong_thieu_im_lang():
    """Doi AGENT_MODEL sang model chua co trong bang gia la chuyen se xay
    ra (2.5 Flash co lich ngung phuc vu). Luc do token van phai hien, tien
    thi bo trong VA noi ro — cong thieu ma khong bao la sai nguy hiem hon
    khong co so."""
    import datetime as dt

    from app.agent import usage

    out = usage._summarize(
        [_series("gemini-2.5-flash", "input", 1_000_000),
         _series("gemini-9-chua-ton-tai", "input", 5_000_000)],
        dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 24))

    assert out["input_tokens"] == 6_000_000  # token van dem du
    assert out["unpriced_models"] == ["gemini-9-chua-ton-tai"]
    assert round(out["cost_usd"], 4) == 0.3  # chi tinh phan biet gia
    hit = [r for r in out["by_model"] if r["model"] == "gemini-9-chua-ton-tai"][0]
    assert hit["cost_usd"] is None


def test_month_usage_loi_monitoring_khong_lam_hong_man_hinh(monkeypatch):
    """Man hinh Agent goi ham nay de hien mot o phu. Thieu quyen hay
    Monitoring tra loi deu KHONG duoc nem exception — cho chat phai chay
    duoc ke ca khi khong biet chi phi."""
    from app.agent import usage

    monkeypatch.setattr(usage, "_cache", None)
    monkeypatch.setattr(usage.settings, "gcp_project_id", "du-an-gia-lap")
    monkeypatch.setattr(
        usage, "_fetch",
        lambda s, e: (_ for _ in ()).throw(RuntimeError("Monitoring API 403: thieu quyen")))

    out = usage.month_usage(force=True)
    assert out["available"] is False
    assert "403" in out["reason"]


def test_agent_usage_chi_danh_cho_team_lead_va_admin(client, monkeypatch):
    """Chi phi ha tang khong phai du lieu nghiep vu — analyst khong xem."""
    da_goi: list[bool] = []

    def gia_lap(force: bool = False) -> dict:
        da_goi.append(force)
        return {"available": True, "cost_usd": 1.23}

    monkeypatch.setattr(main_module.agent, "month_usage", gia_lap)

    assert client.get("/api/agent/usage", headers=as_user(TX)).status_code == 403

    res = client.get("/api/agent/usage", headers=as_user(ADMIN))
    assert res.status_code == 200
    assert res.json()["cost_usd"] == 1.23

    # Nut "Lay lai so moi" trong modal chi phi: force=true phai xuyen xuong
    # den ham doc Monitoring, khong thi bam mai van ra cache 5 phut cu.
    assert client.get("/api/agent/usage?force=true", headers=as_user(ADMIN)).status_code == 200
    assert da_goi == [False, True]


def test_token_log_gom_ca_hai_duong_goi_trong_mot_luot():
    """Mot luot chat goi Vertex AI hai duong (ADK Runner + sql_gen) — ca
    hai phai roi vao cung mot so tam, neu khong so cua phien se thieu."""
    from app.agent import token_log

    class UsageGiaLap:  # dung hinh dang cua usageMetadata trong google-genai
        prompt_token_count = 10
        candidates_token_count = 4
        thoughts_token_count = 6

    with token_log.collecting() as bucket:
        token_log.add_response("gemini-2.5-flash", UsageGiaLap())  # ADK Runner
        token_log.add("gemini-2.5-flash", 3, 1)                    # sql_gen

    # Token "suy nghi" tinh tien nhu token ra nen phai gop vao output: 4 + 6.
    assert bucket == {"gemini-2.5-flash": [13, 11]}


def test_token_log_ngoai_luot_chat_thi_im_lang():
    """Goi Vertex AI ngoai mot luot chat (job nen, test) khong duoc no —
    khong ai phai nho mo context truoc khi goi model."""
    from app.agent import token_log

    token_log.add("gemini-2.5-flash", 5, 5)
    token_log.add_response("gemini-2.5-flash", None)


def test_session_usage_chi_tra_ve_phien_cua_chinh_nguoi_hoi():
    """Dan session_id cua nguoi khac vao URL chi ra bang rong."""
    from app.agent import token_log

    phien = f"test-{uuid.uuid4().hex[:12]}"
    token_log.save(phien, ADMIN, {"gemini-2.5-flash": [1000, 200]})
    try:
        cua_toi = token_log.session_usage(phien, ADMIN)
        assert cua_toi["input_tokens"] == 1000
        assert cua_toi["output_tokens"] == 200
        assert cua_toi["total_tokens"] == 1200
        # 1000 * 0.30e-6 + 200 * 2.50e-6
        assert round(cua_toi["cost_usd"], 8) == round(0.0003 + 0.0005, 8)
        assert cua_toi["by_model"][0]["model"] == "gemini-2.5-flash"

        cua_nguoi_khac = token_log.session_usage(phien, TX)
        assert cua_nguoi_khac["total_tokens"] == 0
        assert cua_nguoi_khac["by_model"] == []
    finally:
        with db() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM agent_token_usage WHERE session_id = %s", (phien,))


def test_session_usage_endpoint_mo_cho_moi_vai_tro(client):
    """Khac so ca thang: day la chi phi cuoc tro chuyen cua chinh nguoi hoi,
    analyst cung duoc xem phan cua minh."""
    from app.agent import token_log

    phien = f"test-{uuid.uuid4().hex[:12]}"
    token_log.save(phien, TX, {"gemini-2.5-flash": [7, 3]})
    try:
        res = client.get(f"/api/agent/usage/session/{phien}", headers=as_user(TX))
        assert res.status_code == 200
        assert res.json()["total_tokens"] == 10

        # Cung URL, nguoi khac hoi: khong 403 ma don gian la khong co gi.
        khac = client.get(f"/api/agent/usage/session/{phien}", headers=as_user(ADMIN))
        assert khac.status_code == 200
        assert khac.json()["total_tokens"] == 0
    finally:
        with db() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM agent_token_usage WHERE session_id = %s", (phien,))
