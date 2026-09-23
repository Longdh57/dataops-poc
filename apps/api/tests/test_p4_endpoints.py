"""Endpoint P4 sinh ra de phuc vu giao dien.

Trong tam van la mot cau hoi: pham vi co ro ri qua duong nao moi khong.
Dropdown bo loc, so lieu dashboard va chi tiet vi pham deu la duong moi.
"""

import psycopg
import pytest
from conftest import ADMIN, CA, LEAD, TX, as_user

URL = "postgresql://dataops:dataops@localhost:5432/dataops"

SALE = "sale@dataops.test"


def _exception_id(state: str) -> int | None:
    """Mot vi pham CUA LAN NAP DANG DUOC KIEM.

    Lay dung run_id ma QC vua kiem: /api/exceptions chi tra ve lan nap do,
    nen mot vi pham cu cua lan nap truoc se khong doi chieu duoc.
    """
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("SELECT coalesce(qc_run_id, last_run_id) FROM sync_state WHERE id=1")
        run = cur.fetchone()
        if not run or not run[0]:
            return None
        cur.execute("""SELECT id FROM qc_exception
                       WHERE state=%s AND run_id=%s ORDER BY id LIMIT 1""", (state, run[0]))
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
    # Vi pham dem theo pham vi...
    assert tx["exceptions"]["open"] <= admin["exceptions"]["open"]
    # ...nhung cong phat hanh thi TOAN CUC. Analyst Texas phai thay dung
    # con so dang chan phat hanh, ke ca khi no nam o bang khac.
    assert tx["gate"]["locked"] == admin["gate"]["locked"]
    assert tx["gate"]["blocking"] == admin["gate"]["blocking"]


def test_summary_nhan_bo_loc_tren_thanh_cong_cu(client):
    khong_loc = client.get("/api/summary", headers=as_user(ADMIN)).json()
    nam = khong_loc["facts"]["year_min"]  # nam that dang co, khong hard-code
    loc_nam = client.get(f"/api/summary?year={nam}", headers=as_user(ADMIN)).json()
    assert loc_nam["facts"]["rows"] < khong_loc["facts"]["rows"]
    assert loc_nam["facts"]["year_min"] == loc_nam["facts"]["year_max"] == nam


def test_summary_xin_bang_ngoai_pham_vi_thi_rong(client):
    """Doi tham so tren URL khong lay duoc so cua bang khac."""
    r = client.get("/api/summary?state=CA", headers=as_user(TX)).json()
    assert r["facts"]["rows"] == 0


# -------------------------------------------------------- chi tiet vi pham

def test_chi_tiet_vi_pham_ngoai_pham_vi_bi_chan(client):
    exc_id = _exception_id("CA")
    if not exc_id:
        pytest.skip("khong co vi pham CA")
    assert client.get(f"/api/exceptions/{exc_id}", headers=as_user(TX)).status_code == 403


def test_chi_tiet_vi_pham_co_du_thu_panel_can(client):
    exc_id = _exception_id("TX")
    if not exc_id:
        pytest.skip("khong co vi pham TX")
    d = client.get(f"/api/exceptions/{exc_id}", headers=as_user(TX)).json()

    assert d["exception"]["id"] == exc_id
    # Panel chi de DOC va de quyet dinh co mo ticket hay khong — no can
    # biet o nay da co ticket chua, chu khong can so de ghi de.
    assert "ticket" in d and "can_open_ticket" in d
    assert "last_signed" in d and "history" in d


def test_hop_thu_chi_tra_ve_vi_pham_cua_mot_lan_nap(client):
    """Danh sach la anh chup cua lan nap hien tai, khong tich luy qua nhieu lan."""
    r = client.get("/api/exceptions?limit=500", headers=as_user(ADMIN)).json()
    if not r["rows"]:
        pytest.skip("chua co vi pham nao")
    assert r["run_id"]
    assert {x["run_id"] for x in r["rows"]} == {r["run_id"]}


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
    # Chi ticket chan moi chan TAI file. Cong con khoa vi QC chua kiem
    # (run moi, hoac bo luat vua sua o P10) — luc do van tai duoc file cua
    # ban DA KY, vi ban ky da dong bang.
    if not gate["blocking_tickets"]:
        pytest.skip("khong co ticket chan")
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
