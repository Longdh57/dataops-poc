"""Dieu kien ket thuc cua quy trinh chat luong (docs/quy-trinh-chat-luong.md).

Bon cau hoi, va ca bon deu la cau hoi ve TRACH NHIEM chu khong ve ky thuat:

  - Ticket co bat buoc mang dieu kien nghiem thu kiem duoc bang may khong?
  - Nguoi co tu bam dong ticket duoc khong? (khong — do la viec cua QC)
  - Con no ma ky khong phieu duyet thi co qua khong?
  - Ticket dang chan co that su chan khong?
"""

import psycopg
import pytest
from conftest import ADMIN, LEAD, TX, as_user

URL = "postgresql://dataops:dataops@localhost:5432/dataops"

# Database local cung la moi truong demo. Ban ky khong xoa duoc qua API —
# do la co y — nen test phai tu don bang SQL, neu khong moi lan chay lai
# lai them mot ban ky gia vao man hinh cua nguoi khac.
NHAN = "[test]"


def _mot_o_trong(state: str):
    """Mot o co that trong lan nap hien tai va CHUA co ticket nao dang song."""
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("""SELECT f.year, f.state, f.gender, f.name, f.number
                       FROM fact_current f
                       LEFT JOIN ticket t
                         ON t.year=f.year AND t.state=f.state AND t.gender=f.gender
                        AND t.name=f.name AND t.status IN ('open','awaiting_verify')
                       WHERE f.state=%s AND t.id IS NULL
                       LIMIT 1""", (state,))
        return cur.fetchone()


def _don_ticket(tid: int) -> None:
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("DELETE FROM ticket WHERE id=%s", (tid,))
        c.commit()


def _mo_ticket(client, o, blocking: bool, user=ADMIN):
    year, state, gender, name, number = o
    return client.post("/api/tickets", headers=as_user(user), json={
        "year": year, "state": state, "gender": gender, "name": name,
        "title": "so nhap sai, doi chieu ban goc SSA",
        "expected_value": int(number) + 7,
        "evidence": "anh chup bang goc", "blocking": blocking,
    })


# ------------------------------------------------------------------ ticket

def test_ticket_phai_co_dieu_kien_nghiem_thu(client):
    """Thieu `expected_value` thi ticket khong dong duoc bang may — tu choi ngay."""
    o = _mot_o_trong("TX")
    assert o, "can mot o TX chua co ticket"
    r = client.post("/api/tickets", headers=as_user(ADMIN), json={
        "year": o[0], "state": o[1], "gender": o[2], "name": o[3],
        "title": "so nay sai",
    })
    assert r.status_code == 422, r.text


def test_ticket_trung_so_nguon_bi_tu_choi(client):
    """Ky vong bang dung so dang co nghia la khong co gi de sua."""
    o = _mot_o_trong("TX")
    assert o
    r = client.post("/api/tickets", headers=as_user(ADMIN), json={
        "year": o[0], "state": o[1], "gender": o[2], "name": o[3],
        "title": "khong co gi de sua", "expected_value": int(o[4]),
    })
    assert r.status_code == 400


def test_mot_o_chi_co_mot_ticket_dang_song(client):
    o = _mot_o_trong("TX")
    assert o
    a = _mo_ticket(client, o, blocking=False)
    assert a.status_code == 201, a.text
    tid = a.json()["id"]
    try:
        b = _mo_ticket(client, o, blocking=False)
        assert b.status_code == 409
        assert b.json()["detail"]["ticket_id"] == tid
    finally:
        _don_ticket(tid)


def test_nguoi_khong_dong_duoc_ticket(client):
    """Khong co action nao dong ticket. Do la viec cua QC, va day la diem
    quyet dinh cua ca quy trinh: trang thai phai do du lieu chung minh."""
    o = _mot_o_trong("TX")
    assert o
    r = _mo_ticket(client, o, blocking=False)
    tid = r.json()["id"]
    try:
        bad = client.patch(f"/api/tickets/{tid}",
                           json={"action": "close", "reason": "toi da sua roi"},
                           headers=as_user(ADMIN))
        assert bad.status_code == 400

        # Bao da sua thi chi chuyen sang CHO XAC MINH, khong phai dong.
        ok = client.patch(f"/api/tickets/{tid}",
                          json={"action": "mark_fixed", "reason": "team Data bao da sua"},
                          headers=as_user(ADMIN))
        assert ok.status_code == 200
        assert ok.json()["status"] == "awaiting_verify"
    finally:
        _don_ticket(tid)


def test_analyst_khong_mo_duoc_ticket_ngoai_pham_vi(client):
    o = _mot_o_trong("CA")
    if not o:
        pytest.skip("khong co o CA trong")
    r = _mo_ticket(client, o, blocking=False, user=TX)
    assert r.status_code == 403


def test_chi_team_lead_moi_go_duoc_chan(client):
    """Go chan la mot quyet dinh mo cong phat hanh — khong phai bo loc."""
    o = _mot_o_trong("TX")
    assert o
    r = _mo_ticket(client, o, blocking=True)
    tid = r.json()["id"]
    try:
        cam = client.patch(f"/api/tickets/{tid}",
                           json={"action": "set_blocking", "blocking": False,
                                 "reason": "analyst tu go"},
                           headers=as_user(TX))
        assert cam.status_code == 403

        duoc = client.patch(f"/api/tickets/{tid}",
                            json={"action": "set_blocking", "blocking": False,
                                  "reason": "khong anh huong bang dang ban"},
                            headers=as_user(LEAD))
        assert duoc.status_code == 200
        assert duoc.json()["blocking"] is False
    finally:
        _don_ticket(tid)


# ----------------------------------------------------------- cong phat hanh

def test_ticket_chan_thi_khong_ky_va_khong_xuat_duoc(client):
    o = _mot_o_trong("TX")
    assert o
    r = _mo_ticket(client, o, blocking=True)
    tid = r.json()["id"]
    try:
        g = client.get("/api/gate", headers=as_user(LEAD)).json()
        assert g["locked"] is True
        assert tid in [t["id"] for t in g["blocking_tickets"]]

        ky = client.post("/api/release",
                         json={"label": "ban thu", "approval_note": "co gang lach qua"},
                         headers=as_user(LEAD))
        assert ky.status_code == 409
        assert ky.json()["detail"]["so_ticket"] >= 1

        xuat = client.post("/api/exports", json={"format": "csv"}, headers=as_user(LEAD))
        assert xuat.status_code == 409
    finally:
        _don_ticket(tid)


def test_vi_pham_luat_khong_tu_khoa_cong(client):
    """Doi nghia so voi P3: vi pham la nghi ngo cua may, khong phai ket luan.

    Con vi pham ma khong con ticket chan thi cong phai MO — nguoi chiu
    trach nhiem duyet, khong phai QC phu quyet.
    """
    g = client.get("/api/gate", headers=as_user(LEAD)).json()
    if g["blocking_tickets"] or g["qc_stale"]:
        pytest.skip("dang bi chan boi ticket hoac QC cu")
    if not g["violations"]["total"]:
        pytest.skip("khong con vi pham nao de test")
    assert g["locked"] is False
    assert g["needs_approval"] is True


def test_con_no_ma_ky_khong_phieu_duyet_thi_bi_tu_choi(client):
    g = client.get("/api/gate", headers=as_user(LEAD)).json()
    if g["locked"] or not g["needs_approval"]:
        pytest.skip("khong con no, hoac dang bi khoa")

    r = client.post("/api/release", json={"label": "ky chay"}, headers=as_user(LEAD))
    assert r.status_code == 422
    assert r.json()["detail"]["so_vi_pham"] >= 0


def test_ky_kem_phieu_duyet_thi_ghi_lai_du_mon_no(client):
    g = client.get("/api/gate", headers=as_user(LEAD)).json()
    if g["locked"]:
        pytest.skip("dang bi khoa")

    note = "3 o duoi nguong la so that cua bang nho, da doi chieu SSA"
    r = client.post("/api/release",
                    json={"label": f"{NHAN} ky kem phieu duyet", "approval_note": note},
                    headers=as_user(LEAD))
    assert r.status_code == 200, r.text
    d = r.json()

    # Nhan thoi thi rong: ban ky phai tu noi duoc no gom gi va no gi.
    assert d["checksum"], "thieu van tay du lieu"
    assert d["violations_fingerprint"], "thieu van tay tap vi pham"
    assert "rules_version" in d and "open_tickets" in d

    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("""SELECT checksum, violations, violations_fingerprint,
                              rules_version, approval_note
                       FROM signed_version WHERE id=%s""", (d["id"],))
        row = cur.fetchone()
    assert row[0] == d["checksum"]
    assert row[2] == d["violations_fingerprint"]
    if g["needs_approval"]:
        assert row[4] == note, "phieu duyet phai di theo ban ky"

    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("DELETE FROM signed_version WHERE id=%s", (d["id"],))
        c.commit()


def test_analyst_khong_duoc_ky(client):
    r = client.post("/api/release", json={"label": "analyst thu ky"}, headers=as_user(TX))
    assert r.status_code == 403
    assert "team_lead" in r.json()["detail"]


# ------------------------------------------------------------------- facts

def test_facts_tra_ve_so_cua_nguon_chu_khong_sua(client):
    """Khong con duong nao lam so doc ra khac so trong fact_current."""
    o = _mot_o_trong("TX")
    assert o
    year, state, gender, name, number = o
    r = _mo_ticket(client, o, blocking=False)
    tid = r.json()["id"]
    try:
        res = client.get(f"/api/facts?state={state}&year={year}&gender={gender}&name={name}",
                         headers=as_user(ADMIN)).json()
        row = next(x for x in res["rows"] if x["name"] == name)
        # Ticket doi so thanh number+7, nhung API van tra ve so cua nguon.
        assert row["number"] == number
        assert row["ticket_id"] == tid
        assert row["ticket_expected"] == str(number + 7)
    finally:
        _don_ticket(tid)
