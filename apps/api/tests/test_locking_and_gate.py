"""Dieu kien ket thuc P3, ve khoa lac quan:

'Hai phien sua cung mot dong thi phien sau nhan 409, khong ghi de.'

Va cong phat hanh: con ngoai le nghiem trong thi khong ai ky duoc.
"""

import psycopg
import pytest
from conftest import ADMIN, LEAD, TX, as_user

URL = "postgresql://dataops:dataops@localhost:5432/dataops"


def _mot_ngoai_le_dang_mo(state=None):
    """Lay mot ngoai le open co du khoa tu nhien de sua duoc."""
    where = "status='open' AND name IS NOT NULL AND year IS NOT NULL"
    if state:
        where += f" AND state='{state}'"
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute(f"SELECT id, year, state, gender, name FROM qc_exception WHERE {where} LIMIT 1")
        return cur.fetchone()


def test_khoa_lac_quan_phien_sau_nhan_409(client):
    exc = _mot_ngoai_le_dang_mo()
    assert exc, "can it nhat mot ngoai le dang mo de test"
    exc_id = exc[0]

    # Phien A sua truoc — thanh cong
    a = client.patch(f"/api/exceptions/{exc_id}",
                     json={"action": "apply", "new_value": 999,
                           "reason": "phien A sua", "expected_version": 0},
                     headers=as_user(ADMIN))
    assert a.status_code == 200, a.text
    assert a.json()["version"] == 1

    # Phien B cam ban cu (version 0) sua cung dong -> phai bi chan
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("UPDATE qc_exception SET status='open', resolved_at=NULL WHERE id=%s", (exc_id,))
        c.commit()

    b = client.patch(f"/api/exceptions/{exc_id}",
                     json={"action": "apply", "new_value": 111,
                           "reason": "phien B sua", "expected_version": 0},
                     headers=as_user(ADMIN))
    assert b.status_code == 409, f"phien sau phai bi chan, nhung nhan {b.status_code}"

    d = b.json()["detail"]
    assert d["current_version"] == 1
    assert d["expected_version"] == 0
    # 409 phai kem diff de nguoi dung tu quyet dinh
    assert d["gia_tri_hien_tai"] == 999
    assert d["gia_tri_ban_muon_ghi"] == 111

    # Va quan trong nhat: KHONG ghi de
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("""SELECT new_value FROM fact_override
                       WHERE year=%s AND state=%s AND gender=%s AND name=%s AND field='number'""",
                    exc[1:])
        assert cur.fetchone()[0] == "999", "phien B da ghi de mat du lieu cua phien A"


def test_analyst_khong_sua_duoc_dong_ngoai_pham_vi(client):
    exc = _mot_ngoai_le_dang_mo(state="CA")
    if not exc:
        pytest.skip("khong co ngoai le CA")
    r = client.patch(f"/api/exceptions/{exc[0]}",
                     json={"action": "park", "reason": "thu sua ngoai pham vi"},
                     headers=as_user(TX))
    assert r.status_code == 403


def test_cong_phat_hanh_khoa_khi_con_ngoai_le_nghiem_trong(client):
    g = client.get("/api/gate", headers=as_user(LEAD)).json()
    if not g["locked"]:
        pytest.skip("cong dang mo, khong co gi de test")

    r = client.post("/api/release", json={"label": "ban thu"}, headers=as_user(LEAD))
    assert r.status_code == 409
    assert r.json()["detail"]["ngoai_le_nghiem_trong_con_mo"] > 0


def test_khong_tai_duoc_file_khi_cong_con_khoa(client):
    g = client.get("/api/gate", headers=as_user(LEAD)).json()
    if not g["locked"]:
        pytest.skip("cong dang mo")
    r = client.post("/api/exports", json={"format": "csv"}, headers=as_user(LEAD))
    assert r.status_code == 409


def test_analyst_khong_duoc_ky(client):
    r = client.post("/api/release", json={"label": "analyst thu ky"}, headers=as_user(TX))
    assert r.status_code == 403
    assert "team_lead" in r.json()["detail"]


def test_override_hien_ra_trong_facts(client):
    """So da sua phai thay the so goc khi doc."""
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("""SELECT year, state, gender, name, new_value FROM fact_override
                       WHERE field='number' LIMIT 1""")
        ov = cur.fetchone()
    if not ov:
        pytest.skip("chua co override nao")
    year, state, gender, name, new_value = ov
    r = client.get(f"/api/facts?state={state}&year={year}&gender={gender}&name={name}",
                   headers=as_user(ADMIN))
    rows = [x for x in r.json()["rows"] if x["name"] == name]
    assert rows, "khong tim thay dong da override"
    assert rows[0]["number"] == int(new_value)
    assert rows[0]["overridden"] is True
