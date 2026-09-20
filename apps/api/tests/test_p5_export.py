"""P5: file gui khach phai giai thich duoc bang dung mot dong trong bang.

Ba cau hoi: xuat tu ban ky nao, dinh dang gi, pham vi cua ai. Cac test
duoi day giu cho ba cau tra loi do luon duoc ghi lai.
"""

import psycopg
import pytest
from conftest import ADMIN, LEAD, as_user

URL = "postgresql://dataops:dataops@localhost:5432/dataops"
SALE = "sale@dataops.test"

# Nhan de nhan ra thu do test tao ra. Database local cung la moi truong
# demo, nen test phai don sach sau khi chay — khong thi moi lan chay lai
# lai them mot nam yeu cau file gia vao man hinh cua nguoi khac.
NHAN = "[test]"


@pytest.fixture(autouse=True)
def don_dep():
    yield
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("""DELETE FROM export_job
                       WHERE signed_version_id IN
                             (SELECT id FROM signed_version WHERE label LIKE %s)""",
                    (f"{NHAN}%",))
        cur.execute("DELETE FROM signed_version WHERE label LIKE %s", (f"{NHAN}%",))
        c.commit()


def _gate_mo(client) -> bool:
    return not client.get("/api/gate", headers=as_user(ADMIN)).json()["locked"]


def _row(sql: str, args=()):
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone()


# Ban ky trong moi truong test gan nhu luon con no (du lieu mau co san vi
# pham), nen moi lan ky deu phai kem phieu duyet — dung nhu nguoi that.
PHIEU = "ban kiem thu tu dong, khong gui khach"


def _ky_ban_tam(client) -> int:
    """Ky mot ban mang nhan test de fixture don duoc sau do."""
    r = client.post("/api/release",
                    json={"label": f"{NHAN} ban de xin file", "approval_note": PHIEU},
                    headers=as_user(LEAD))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_ky_dong_bang_danh_sach_lan_nap(client):
    """Thieu danh sach nay thi Export Job khong biet ban ky gom nhung gi."""
    if not _gate_mo(client):
        pytest.skip("cong dang khoa, khong ky duoc")

    r = client.post("/api/release",
                    json={"label": f"{NHAN} dong bang lan nap", "approval_note": PHIEU},
                    headers=as_user(LEAD))
    assert r.status_code == 200, r.text
    runs = r.json()["source_run_ids"]
    assert runs, "ban ky phai ghi lai nhung lan nap du lieu nam trong no"

    trong_db = _row("SELECT source_run_ids FROM signed_version WHERE id = %s", (r.json()["id"],))
    assert trong_db[0] == runs

    trong_sync = _row("SELECT source_run_ids FROM sync_state WHERE id = 1")
    assert runs == trong_sync[0], "phai dung danh sach ban sao dang giu"

    # Va ban ky phai tu noi duoc no gom gi: van tay du lieu bat duoc truong
    # hop team Data sua so TAI CHO duoi cung mot run_id — luc do nhan van
    # the ma so da khac.
    assert r.json()["checksum"], "ban ky phai co van tay du lieu"


def test_xin_file_ghi_lai_dinh_dang_va_pham_vi_cua_nguoi_xin(client):
    if not _gate_mo(client):
        pytest.skip("cong dang khoa")
    ban_ky = _ky_ban_tam(client)

    r = client.post("/api/exports", json={"format": "xlsx"}, headers=as_user(SALE))
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["format"] == "xlsx"
    assert body["scope"] == ["CA", "TX"], "pham vi phai chot ngay luc xin file"
    assert body["signed_version"]["id"] == ban_ky

    job = _row("""SELECT format, scope_states, signed_version_id
                  FROM export_job WHERE id = %s""", (body["job_id"],))
    assert job[0] == "xlsx"
    assert job[1] == ["CA", "TX"]
    assert job[2] == ban_ky


def test_admin_xin_file_thi_khong_bi_gioi_han_bang(client):
    if not _gate_mo(client):
        pytest.skip("cong dang khoa")
    _ky_ban_tam(client)

    body = client.post("/api/exports", json={"format": "csv"}, headers=as_user(ADMIN)).json()
    assert body["scope"] is None
    assert _row("SELECT scope_states FROM export_job WHERE id = %s", (body["job_id"],))[0] is None


def test_xin_file_luon_gan_vao_ban_ky_gan_nhat(client):
    if not _gate_mo(client):
        pytest.skip("cong dang khoa")
    moi_nhat = _ky_ban_tam(client)

    body = client.post("/api/exports", json={"format": "csv"}, headers=as_user(SALE)).json()
    assert body["signed_version"]["id"] == moi_nhat


def test_khong_kich_hoat_duoc_job_thi_van_giu_yeu_cau_trong_hang_doi(client):
    """Duoi local khong co Cloud Run. Yeu cau van phai duoc ghi nhan.

    Neu API nem loi o day, nguoi dung mat trang trong khi dong export_job
    da nam trong database — trang thai te nhat: da ghi ma nguoi dung tuong
    la chua.
    """
    if not _gate_mo(client):
        pytest.skip("cong dang khoa")
    _ky_ban_tam(client)

    body = client.post("/api/exports", json={"format": "csv"}, headers=as_user(SALE)).json()
    assert body["status"] == "pending"
    assert body["triggered"] is False
    assert "dataops-export" in body["note"] or "GCP_PROJECT_ID" in body["note"]
    assert _row("SELECT status FROM export_job WHERE id = %s", (body["job_id"],))[0] == "pending"


def test_chi_nhan_csv_va_xlsx(client):
    r = client.post("/api/exports", json={"format": "pdf"}, headers=as_user(SALE))
    assert r.status_code == 400
