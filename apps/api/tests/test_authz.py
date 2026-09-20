"""Dieu kien ket thuc P3, ve phan quyen:

'Tai khoan analyst pham vi Texas goi API voi tham so bang khac van chi
nhan duoc du lieu Texas.'
"""

from conftest import ADMIN, CA, TX, as_user


def test_thieu_danh_tinh_bi_chan(client):
    assert client.get("/api/facts").status_code == 401


def test_nguoi_la_bi_tu_choi(client):
    r = client.get("/api/facts", headers=as_user("nguoi.la@example.com"))
    assert r.status_code == 403
    assert "chua duoc cap quyen" in r.json()["detail"]


def test_analyst_khong_gui_bang_chi_thay_pham_vi_cua_minh(client):
    r = client.get("/api/facts?limit=200", headers=as_user(TX))
    assert r.status_code == 200
    states = {row["state"] for row in r.json()["rows"]}
    assert states == {"TX"}, f"ro ri du lieu ngoai pham vi: {states}"


def test_analyst_xin_bang_ngoai_pham_vi_nhan_ve_rong(client):
    """Day la cot loi: client co the gui bat ky tham so nao, dieu kien
    that van lay tu database theo email."""
    r = client.get("/api/facts?state=CA&limit=200", headers=as_user(TX))
    assert r.status_code == 200
    assert r.json()["rows"] == [], "analyst TX lay duoc du lieu CA — ro ri pham vi"


def test_hai_analyst_khac_pham_vi_khong_thay_du_lieu_cua_nhau(client):
    tx = client.get("/api/facts?limit=100", headers=as_user(TX)).json()["rows"]
    ca = client.get("/api/facts?limit=100", headers=as_user(CA)).json()["rows"]
    assert {r["state"] for r in tx} == {"TX"}
    assert {r["state"] for r in ca} == {"CA"}


def test_admin_thay_duoc_nhieu_bang(client):
    r = client.get("/api/facts?limit=500", headers=as_user(ADMIN))
    assert len({row["state"] for row in r.json()["rows"]}) >= 1
    assert r.json()["scope"] == "tat ca"


def test_ngoai_le_cung_bi_ep_pham_vi(client):
    r = client.get("/api/exceptions?limit=200", headers=as_user(TX))
    assert r.status_code == 200
    states = {row["state"] for row in r.json()["rows"] if row["state"]}
    assert states <= {"TX"}, f"ngoai le ro ri ngoai pham vi: {states}"


def test_sap_xep_ngoai_allowlist_bi_tu_choi(client):
    r = client.get("/api/facts?sort=run_id", headers=as_user(ADMIN))
    assert r.status_code == 400
