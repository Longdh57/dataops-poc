"""Danh dau vi pham QC tren luoi du lieu.

Luoi du lieu khong con chi la bang so: dong nao dang vi pham luat thi
mang mot cham mau. Bon cau hoi o day, va khong cau nao la cau hoi ve
giao dien:

  - Cham dem DUNG so luat dong do dang vi pham, va mang muc NANG NHAT?
  - Vi pham cap nhom (institution_id NULL) co bi dan nham vao tung dong?
  - Vi pham cua lan QC khac co lot vao khong?
  - Hop chi tiet co ro ri o ngoai pham vi khong?

Bai test tu dung du lieu cua chinh no — ba dong gia o mot nam khong co
that — roi don sach. Nho vay no chay duoc tren database trong, khong can
doi den lan seed 1,2 trieu dong.
"""

import os

import psycopg
import pytest
from conftest import ADMIN, CA, TX, as_user

# Mac dinh la Postgres cua docker compose nhin tu may host — giong cac file
# test khac. Doc them bien moi truong de chay duoc ca tu trong container,
# noi database ten la `db` chu khong phai `localhost`.
URL = os.environ.get("DATABASE_URL", "postgresql://dataops:dataops@localhost:5432/dataops")

# Nam khong co trong FDIC SOD that, nen ba dong gia khong bao gio dung do
# voi du lieu that dang nam trong bang.
NAM = 1901
RUN = "test-facts-violations"
ID_MOT, ID_HAI, ID_BA = 990001, 990002, 990003


@pytest.fixture
def o_gia():
    """Ba dong TX + vi pham cua CHINH lan QC hien tai, don sach sau bai test.

    Vi pham phai mang dung `qc_run_id` dang nam trong sync_state: /api/facts
    chi dem vi pham cua lan QC do, nen mot run_id tu bia se khong hien ra
    cham nao va bai test se xanh vi ly do sai.
    """
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("SELECT qc_run_id FROM sync_state WHERE id = 1")
        row = cur.fetchone()
        if not row or not row[0]:
            pytest.skip("chua co lan QC nao de gan vi pham vao")
        qc_run = row[0]

        cur.execute(
            """INSERT INTO fact_current
                   (year, state, institution_id, institution, run_id, deposit,
                    deposit_share, prev_deposit, prev_year)
               VALUES (%s,'TX',%s,'Bank Mot',%s, 900, 0.5, 100, %s),
                      (%s,'TX',%s,'Bank Hai',%s, 500, 0.3, 480, %s),
                      (%s,'TX',%s,'Bank Ba', %s, 100, 0.2,  90, %s)""",
            (NAM, ID_MOT, RUN, NAM - 1, NAM, ID_HAI, RUN, NAM - 1,
             NAM, ID_BA, RUN, NAM - 1))

        cur.execute(
            """INSERT INTO qc_exception
                   (run_id, rule_id, severity, year, state, institution_id,
                    institution, message, observed)
               VALUES
                 -- Bank Mot vi pham hai luat: cham phai la mau cua muc nang nhat
                 (%s, 'test_spike', 'critical', %s, 'TX', %s, 'Bank Mot',
                  'tang qua 15 lan', '{"deposit": 900}'),
                 (%s, 'test_change', 'warning',  %s, 'TX', %s, 'Bank Mot',
                  'doi qua 300%%', '{"change_pct": 800}'),
                 -- Bank Hai chi mot luat, muc warning
                 (%s, 'test_change', 'warning',  %s, 'TX', %s, 'Bank Hai',
                  'doi qua 300%%', '{"change_pct": 4}'),
                 -- Cap nhom: khong thuoc rieng dong nao
                 (%s, 'test_group',  'critical', %s, 'TX', NULL, NULL,
                  'tong thi phan lech 100%%', '{"total_share": 1.2}'),
                 -- Lan QC khac: khong duoc tinh cho Bank Ba
                 (%s, 'test_am',     'critical', %s, 'TX', %s, 'Bank Ba',
                  'deposit am', '{"deposit": -1}')""",
            (qc_run, NAM, ID_MOT, qc_run, NAM, ID_MOT, qc_run, NAM, ID_HAI,
             qc_run, NAM, f"{qc_run}-cu", NAM, ID_BA))
        c.commit()

    yield {"qc_run": qc_run}

    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("DELETE FROM qc_exception WHERE year = %s AND rule_id LIKE 'test\\_%%'", (NAM,))
        cur.execute("DELETE FROM fact_current WHERE run_id = %s", (RUN,))
        c.commit()


def _dong(client, user=ADMIN) -> dict[int, dict]:
    r = client.get(f"/api/facts?state=TX&year={NAM}&limit=50", headers=as_user(user))
    assert r.status_code == 200, r.text
    return {d["institution_id"]: d for d in r.json()["rows"]}


# ------------------------------------------------------------ cham tren luoi

def test_cham_dem_dung_so_luat_va_lay_muc_nang_nhat(client, o_gia):
    d = _dong(client)
    assert d[ID_MOT]["violations"] == 2
    # Hai luat, mot critical mot warning — cham phai do, khong phai vang.
    assert d[ID_MOT]["violation_severity"] == "critical"
    assert d[ID_HAI]["violations"] == 1
    assert d[ID_HAI]["violation_severity"] == "warning"


def test_dong_sach_khong_co_cham(client, o_gia):
    """Khong co vi pham thi severity phai la NULL chu khong phai 'info'.

    Day la cho de sai nhat trong ca tinh nang: aggregate tren tap rong van
    tra ve mot dong, nen thieu chan thi moi dong sach deu doi mot cham.
    """
    d = _dong(client)
    assert d[ID_BA]["violations"] == 0
    assert d[ID_BA]["violation_severity"] is None


def test_vi_pham_cap_nhom_khong_dan_vao_tung_dong(client, o_gia):
    """Tong thi phan ca bang lech thi khong dong nao rieng le co loi.

    Dan canh bao do len ca ba dong la bao sai cho hai dong vo can — va
    tren du lieu that thi la ca nghin dong.
    """
    d = _dong(client)
    assert sum(x["violations"] for x in d.values()) == 3  # 2 + 1, khong co cai thu tu


def test_vi_pham_cua_lan_qc_khac_khong_lot_vao(client, o_gia):
    d = _dong(client)
    assert d[ID_BA]["violations"] == 0


def test_facts_noi_ro_cham_thuoc_lan_qc_nao(client, o_gia):
    r = client.get(f"/api/facts?state=TX&year={NAM}&limit=50", headers=as_user(ADMIN)).json()
    assert r["qc_run_id"] == o_gia["qc_run"]
    assert "qc_stale" in r and "qc_stale_reason" in r


# --------------------------------------------------------- hop chi tiet o

def test_chi_tiet_tra_ve_dung_luat_nang_nhat_truoc(client, o_gia):
    r = client.get(
        f"/api/facts/violations?year={NAM}&state=TX&institution_id={ID_MOT}",
        headers=as_user(ADMIN))
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert [x["rule_id"] for x in rows] == ["test_spike", "test_change"]
    assert rows[0]["severity"] == "critical"
    # Hop phai du de doc ma khong phai sang man hinh khac: loi va so lieu.
    assert rows[0]["message"] and rows[0]["observed"] == {"deposit": 900}


def test_chi_tiet_khong_tra_ve_vi_pham_cap_nhom(client, o_gia):
    """Hop cua mot dong chi noi ve dong do."""
    r = client.get(
        f"/api/facts/violations?year={NAM}&state=TX&institution_id={ID_HAI}",
        headers=as_user(ADMIN)).json()
    assert [x["rule_id"] for x in r["rows"]] == ["test_change"]


def test_chi_tiet_ngoai_pham_vi_bi_chan(client, o_gia):
    """Doi tham so tren URL khong doc duoc vi pham cua bang khac."""
    r = client.get(
        f"/api/facts/violations?year={NAM}&state=TX&institution_id={ID_MOT}",
        headers=as_user(CA))
    assert r.status_code == 403


def test_chi_tiet_trong_pham_vi_van_doc_duoc(client, o_gia):
    r = client.get(
        f"/api/facts/violations?year={NAM}&state=TX&institution_id={ID_MOT}",
        headers=as_user(TX))
    assert r.status_code == 200
    assert len(r.json()["rows"]) == 2


def test_o_sach_tra_ve_danh_sach_rong(client, o_gia):
    r = client.get(
        f"/api/facts/violations?year={NAM}&state=TX&institution_id={ID_BA}",
        headers=as_user(ADMIN)).json()
    assert r["rows"] == [] and r["ticket"] is None
