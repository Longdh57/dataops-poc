"""Man hinh Nguoi dung & phan quyen: tao tai khoan ngay trong ung dung.

Bon dieu phai chac, va test o day bam vao dung bon dieu do:

  - Chi admin dung duoc /api/users, ca doc lan ghi. Bo chon danh tinh di
    duong rieng (/api/users/switchable, chi che do dev) va mo cho moi vai
    tro — doi mot lan ma khong doi lai duoc thi ban demo coi nhu het.
  - Pham vi vua gan phai CO HIEU LUC THAT o tang du lieu, khong chi hien
    dep tren man hinh. Day la ly do bai test cuoi goi /api/facts.
  - Analyst khong duoc de trong pham vi: trong nghia la KHONG GIOI HAN
    (authz.scope_clause), tuc la cap nham toan bo chu khong phai cap thieu.
  - Admin khong tu ha quyen / tu xoa duoc chinh minh — cu bam khong go lai
    duoc, vi mat quyen admin la mat luon man hinh nay.

Test ghi vao database local, nen moi tai khoan tao ra deu mang duoi
`@test-users.local` va fixture `don_dep` xoa het sau moi bai.
"""

import os
import uuid

import psycopg
import pytest
from conftest import ADMIN, LEAD, TX, as_user

# conftest da dat san gia tri mac dinh. Doc tu moi truong chu khong go
# cung "localhost" de bai test chay duoc ca tu host lan tu trong container.
URL = os.environ["DATABASE_URL"]
DOMAIN = "@test-users.local"


@pytest.fixture(autouse=True)
def don_dep():
    yield
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("DELETE FROM app_user WHERE email LIKE %s", (f"%{DOMAIN}",))
        c.commit()


def tao(client, email: str, role: str, scope=None, who: str = ADMIN):
    body = {"email": email, "display_name": "Test", "role": role}
    if scope is not None:
        body["scope_states"] = scope
    return client.post("/api/users", json=body, headers=as_user(who))


# ----------------------------------------------------------------- doc

def test_chi_admin_doc_duoc_danh_sach_quan_tri(client):
    """Cap quyen la viec cua mot vai tro — xem ai dang co quyen gi cung vay."""
    assert client.get("/api/users", headers=as_user(TX)).status_code == 403
    assert client.get("/api/users", headers=as_user(LEAD)).status_code == 403

    r = client.get("/api/users", headers=as_user(ADMIN))
    assert r.status_code == 200
    assert r.json()["roles"] == ["admin", "team_lead", "analyst"]


def test_bo_chon_danh_tinh_mo_cho_moi_vai_tro_o_che_do_dev(client):
    """Duong rieng, khong phai /api/users: doi sang analyst mot lan roi
    khong doi lai duoc thi ban demo coi nhu het."""
    r = client.get("/api/users/switchable", headers=as_user(TX))
    assert r.status_code == 200
    assert any(u["email"] == ADMIN for u in r.json()["rows"])


def test_bo_chon_danh_tinh_khong_ro_ri_gi_ngoai_cai_no_ve_ra(client):
    r = client.get("/api/users/switchable", headers=as_user(TX))
    assert set(r.json()["rows"][0]) == {"email", "display_name", "role", "scope_states"}


def test_bo_chon_danh_tinh_bo_qua_tai_khoan_da_tat(client):
    email = f"da.tat{DOMAIN}"
    uid = tao(client, email, "analyst", ["TX"]).json()["id"]
    client.put(f"/api/users/{uid}",
               json={"role": "analyst", "scope_states": ["TX"], "is_active": False},
               headers=as_user(ADMIN))
    rows = client.get("/api/users/switchable", headers=as_user(TX)).json()["rows"]
    assert email not in {u["email"] for u in rows}


def test_moi_dong_co_dung_mot_vai_tro(client):
    """Man hinh chi ghi mot vai tro moi nguoi — doc ra cung phai the."""
    for u in client.get("/api/users", headers=as_user(ADMIN)).json()["rows"]:
        assert isinstance(u["role"], str) or u["role"] is None


# ----------------------------------------------------------------- ghi

def test_chi_admin_tao_duoc(client):
    r = tao(client, f"a{DOMAIN}", "analyst", ["TX"], who=LEAD)
    assert r.status_code == 403
    assert tao(client, f"a{DOMAIN}", "analyst", ["TX"], who=TX).status_code == 403


def test_tao_analyst_thanh_cong_va_chuan_hoa_email_pham_vi(client):
    r = tao(client, f"Hoa.Nguyen{DOMAIN}".upper(), "analyst", ["tx", "ca"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == f"hoa.nguyen{DOMAIN}"
    assert body["scope_states"] == ["CA", "TX"]
    assert body["role"] == "analyst" and body["is_active"] is True


def test_email_sai_dinh_dang_bi_tu_choi(client):
    assert tao(client, "khong-phai-email", "team_lead").status_code == 422


def test_email_trung_bi_tu_choi(client):
    assert tao(client, f"trung{DOMAIN}", "team_lead").status_code == 201
    assert tao(client, f"TRUNG{DOMAIN}", "analyst", ["TX"]).status_code == 409


def test_vai_tro_ngoai_danh_sach_bi_tu_choi(client):
    assert tao(client, f"x{DOMAIN}", "sysadmin", ["TX"]).status_code == 422


def test_analyst_khong_duoc_de_trong_pham_vi(client):
    """De trong KHONG phai 'chua cap gi' ma la 'khong gioi han'."""
    assert tao(client, f"rong{DOMAIN}", "analyst", []).status_code == 422
    assert tao(client, f"rong{DOMAIN}", "analyst", None).status_code == 422


def test_team_lead_khong_giu_pham_vi_du_client_co_gui(client):
    r = tao(client, f"lead{DOMAIN}", "team_lead", ["TX"])
    assert r.status_code == 201
    assert r.json()["scope_states"] is None, "vai tro khong gioi han ma van bi gan pham vi"


# ---------------------------------------------------------------- sua/xoa

def test_sua_thay_the_vai_tro_chu_khong_cong_don(client):
    uid = tao(client, f"doi{DOMAIN}", "analyst", ["TX"]).json()["id"]
    r = client.put(f"/api/users/{uid}",
                   json={"display_name": "Doi", "role": "team_lead", "is_active": True},
                   headers=as_user(ADMIN))
    assert r.status_code == 200
    assert r.json()["role"] == "team_lead"
    assert r.json()["scope_states"] is None

    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("SELECT count(*) FROM app_role WHERE user_id = %s", (uid,))
        assert cur.fetchone()[0] == 1, "vai tro cu con sot lai — pham vi cu song theo"


def test_tat_tai_khoan_thi_khong_goi_duoc_api(client):
    email = f"tat{DOMAIN}"
    uid = tao(client, email, "analyst", ["TX"]).json()["id"]
    assert client.get("/api/me", headers=as_user(email)).status_code == 200

    client.put(f"/api/users/{uid}",
               json={"role": "analyst", "scope_states": ["TX"], "is_active": False},
               headers=as_user(ADMIN))
    r = client.get("/api/me", headers=as_user(email))
    assert r.status_code == 403
    assert "vo hieu hoa" in r.json()["detail"]


def test_admin_khong_tu_ha_quyen_hoac_tu_xoa(client):
    me = next(u for u in client.get("/api/users", headers=as_user(ADMIN)).json()["rows"]
              if u["email"] == ADMIN)
    r = client.put(f"/api/users/{me['id']}",
                   json={"role": "analyst", "scope_states": ["TX"], "is_active": True},
                   headers=as_user(ADMIN))
    assert r.status_code == 409
    assert client.delete(f"/api/users/{me['id']}", headers=as_user(ADMIN)).status_code == 409
    # va van con nguyen quyen
    assert client.get("/api/me", headers=as_user(ADMIN)).json()["roles"] == ["admin"]


def test_xoa_roi_thi_khong_vao_duoc_nua(client):
    email = f"xoa{DOMAIN}"
    uid = tao(client, email, "analyst", ["TX"]).json()["id"]
    assert client.delete(f"/api/users/{uid}", headers=as_user(ADMIN)).status_code == 200
    assert client.get("/api/me", headers=as_user(email)).status_code == 403
    assert client.delete(f"/api/users/{uid}", headers=as_user(ADMIN)).status_code == 404


def test_moi_thao_tac_deu_co_dau_vet(client):
    # audit_log khong bao gio bi xoa — ke ca giua cac lan chay test. Email
    # duy nhat moi lan la cach duy nhat de doc dung dau vet cua bai nay.
    email = f"vet-{uuid.uuid4().hex[:8]}{DOMAIN}"
    uid = tao(client, email, "analyst", ["TX"]).json()["id"]
    client.put(f"/api/users/{uid}",
               json={"role": "analyst", "scope_states": ["CA"], "is_active": True},
               headers=as_user(ADMIN))
    client.delete(f"/api/users/{uid}", headers=as_user(ADMIN))

    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("""SELECT action FROM audit_log
                       WHERE entity = 'app_user' AND entity_key = %s ORDER BY id""", (email,))
        assert [r[0] for r in cur.fetchall()] == ["user_create", "user_update", "user_delete"]


# ------------------------------------------------- pham vi co hieu luc that

def test_pham_vi_vua_gan_co_hieu_luc_ngay_o_tang_du_lieu(client):
    """Cot loi: cap quyen tren man hinh phai la cap quyen THAT.

    Tai khoan moi pham vi [TX] goi ?state=CA van nhan ve rong — dieu kien
    lay tu database theo email, khong lay tu tham so client.
    """
    email = f"pham.vi{DOMAIN}"
    assert tao(client, email, "analyst", ["TX"]).status_code == 201

    r = client.get("/api/facts?limit=200", headers=as_user(email))
    assert r.status_code == 200
    assert {row["state"] for row in r.json()["rows"]} == {"TX"}
    assert client.get("/api/facts?state=CA&limit=50", headers=as_user(email)).json()["rows"] == []
