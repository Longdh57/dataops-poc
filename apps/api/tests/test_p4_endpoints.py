"""Endpoint P4 sinh ra de phuc vu giao dien.

Trong tam van la mot cau hoi: pham vi co ro ri qua duong nao moi khong.
Dropdown bo loc, so lieu dashboard va chi tiet ngoai le deu la duong moi.
"""

import psycopg
import pytest
from conftest import ADMIN, CA, LEAD, TX, as_user

URL = "postgresql://dataops:dataops@localhost:5432/dataops"

SALE = "sale@dataops.test"


def _exception_id(state: str) -> int | None:
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("SELECT id FROM qc_exception WHERE state=%s ORDER BY id LIMIT 1", (state,))
        row = cur.fetchone()
    return row[0] if row else None


# ------------------------------------------------------------------ options

def test_dropdown_chi_hien_bang_trong_pham_vi(client):
    """Danh sach bang trong bo loc cung phai theo pham vi — ro ri ten bang
    cung la ro ri."""
    tx = client.get("/api/options", headers=as_user(TX)).json()
    assert tx["states"] == ["TX"]

    admin = client.get("/api/options", headers=as_user(ADMIN)).json()
    assert len(admin["states"]) > 1 and "CA" in admin["states"]


# ------------------------------------------------------------------ summary

def test_summary_dem_theo_pham_vi(client):
    tx = client.get("/api/summary", headers=as_user(TX)).json()
    admin = client.get("/api/summary", headers=as_user(ADMIN)).json()

    assert tx["scope"] == ["TX"]
    assert 0 < tx["facts"]["rows"] < admin["facts"]["rows"]
    # Ngoai le dem theo pham vi...
    assert tx["exceptions"]["open"] < admin["exceptions"]["open"]
    # ...nhung cong phat hanh thi TOAN CUC. Analyst Texas phai thay dung
    # con so dang chan phat hanh, ke ca khi no nam o bang khac.
    assert tx["gate"] == admin["gate"]


def test_summary_nhan_bo_loc_tren_thanh_cong_cu(client):
    khong_loc = client.get("/api/summary", headers=as_user(ADMIN)).json()
    loc_nam = client.get("/api/summary?year=2021", headers=as_user(ADMIN)).json()
    assert loc_nam["facts"]["rows"] < khong_loc["facts"]["rows"]
    assert loc_nam["facts"]["year_min"] == loc_nam["facts"]["year_max"] == 2021


def test_summary_xin_bang_ngoai_pham_vi_thi_rong(client):
    """Doi tham so tren URL khong lay duoc so cua bang khac."""
    r = client.get("/api/summary?state=CA", headers=as_user(TX)).json()
    assert r["facts"]["rows"] == 0


# ------------------------------------------------------- chi tiet ngoai le

def test_chi_tiet_ngoai_le_ngoai_pham_vi_bi_chan(client):
    exc_id = _exception_id("CA")
    if not exc_id:
        pytest.skip("khong co ngoai le CA")
    assert client.get(f"/api/exceptions/{exc_id}", headers=as_user(TX)).status_code == 403


def test_chi_tiet_ngoai_le_co_du_thu_panel_can(client):
    exc_id = _exception_id("TX")
    if not exc_id:
        pytest.skip("khong co ngoai le TX")
    d = client.get(f"/api/exceptions/{exc_id}", headers=as_user(TX)).json()

    assert d["exception"]["id"] == exc_id
    # expected_version la thu panel phai gui lai khi ap so moi — thieu no
    # thi khoa lac quan khong co gi de so sanh.
    assert "expected_version" in d
    assert "last_signed" in d and "history" in d


# ----------------------------------------------------------------- versions

def test_chi_team_lead_moi_thay_nut_ky(client):
    assert client.get("/api/versions", headers=as_user(LEAD)).json()["can_sign"] is True
    assert client.get("/api/versions", headers=as_user(TX)).json()["can_sign"] is False


def test_analyst_khong_ghi_duoc_da_gui_cho_khach(client):
    r = client.post("/api/versions/1/sent", json={"customer": "Khach A"}, headers=as_user(CA))
    assert r.status_code == 403


# ------------------------------------------------------------------ exports

def test_sale_chi_thay_job_cua_chinh_minh(client):
    rows = client.get("/api/exports", headers=as_user(SALE)).json()["rows"]
    assert all(r["requested_by"] == SALE for r in rows)


def test_tai_file_khi_cong_khoa_bi_chan(client):
    gate = client.get("/api/gate", headers=as_user(ADMIN)).json()
    if not gate["locked"]:
        pytest.skip("cong dang mo")
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("SELECT id FROM export_job ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
    if not row:
        pytest.skip("chua co export job nao")
    r = client.get(f"/api/exports/{row[0]}/download", headers=as_user(ADMIN))
    assert r.status_code == 409


# ------------------------------------------------------------------ rebuild

def test_analyst_khong_duoc_nap_lai_tu_nguon(client):
    """Nut 'Nap lai tu nguon' chay han Sync Job — khong phai ai cung bam duoc."""
    r = client.post("/api/rebuild", headers=as_user(TX))
    assert r.status_code == 403
