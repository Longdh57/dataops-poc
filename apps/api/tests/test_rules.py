"""Bo luat QC (P10): song trong Postgres, sua duoc trong ung dung.

Nam dieu phai chac, va test o day bam vao dung nam dieu do:

  - Catalog tra ve la CHINH bo luat trong DB, va YAML hien kem doc nguoc
    lai ra dung bo luat do.
  - Chi team_lead / admin sua duoc. Luat la quy tac chung — ai cung doc.
  - Khong luu duoc luat hong: sai cau truc, SQL loi, thieu cot, SQL ghi.
  - Moi lan ghi la mot version moi co snapshot + audit; ban ky cu tai hien
    duoc bo luat cu ke ca khi luat da bi xoa.
  - Hai nguoi sua cung luc thi nguoi sau nhan 409, khong ghi de.

Test ghi vao database local — moi test ghi deu di qua fixture `bo_luat`
de tra bo luat ve nguyen trang, va chi dung id bat dau bang `test_p10_`.
"""

import json
from pathlib import Path

import psycopg
import pytest
import yaml
from conftest import ADMIN, LEAD, TX, as_user
from psycopg.rows import dict_row

from app import rules as rules_file

URL = "postgresql://dataops:dataops@localhost:5432/dataops"
RULES_YAML = Path(__file__).resolve().parents[3] / "rules" / "rules.yaml"

SQL_OK = """SELECT year, state, institution_id, institution,
       jsonb_build_object('deposit', deposit) AS observed
FROM fact_current WHERE deposit < -999999999"""


@pytest.fixture
def bo_luat():
    """Chup bo luat truoc test, tra lai nguyen trang sau test. Tra ve version."""
    with psycopg.connect(URL, row_factory=dict_row) as c, c.cursor() as cur:
        cur.execute("SELECT * FROM qc_rule")
        rules = cur.fetchall()
        cur.execute("SELECT * FROM qc_ruleset WHERE id = 1")
        rs = cur.fetchone()
    yield rs["version"]
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("DELETE FROM qc_rule")
        for r in rules:
            cur.execute(
                """INSERT INTO qc_rule (id, severity, scope, message, sql, enabled, sort_order,
                                        created_by, created_at, updated_by, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (r["id"], r["severity"], json.dumps(r["scope"]) if r["scope"] else None,
                 r["message"], r["sql"], r["enabled"], r["sort_order"], r["created_by"],
                 r["created_at"], r["updated_by"], r["updated_at"]))
        cur.execute("UPDATE qc_ruleset SET version=%s, updated_by=%s, updated_at=%s, note=%s "
                    "WHERE id = 1", (rs["version"], rs["updated_by"], rs["updated_at"], rs["note"]))
        cur.execute("DELETE FROM qc_ruleset_snapshot WHERE version > %s", (rs["version"],))
        cur.execute("DELETE FROM audit_log WHERE entity = 'qc_rule' AND entity_key LIKE 'test_p10_%%'")
        c.commit()


def _catalog(user=ADMIN, **params):
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app).get("/api/rules", headers=as_user(user), params=params).json()


def _tao(client, version, rule_id="test_p10_a", user=ADMIN, **kw):
    body = {"id": rule_id, "severity": "warning", "message": "test rule", "sql": SQL_OK,
            "expected_version": version, **kw}
    return client.post("/api/rules", headers=as_user(user), json=body)


# ------------------------------------------------------------------ doc

def test_catalog_la_bo_luat_trong_db(client):
    body = client.get("/api/rules", headers=as_user(ADMIN)).json()
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("SELECT id FROM qc_rule ORDER BY sort_order, id")
        ids = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT version FROM qc_ruleset WHERE id = 1")
        version = cur.fetchone()[0]
    assert [r["id"] for r in body["rules"]] == ids
    assert body["version"] == body["current_version"] == version
    assert body["source"] == "qc_rule"
    assert body["snapshot"] is False


def test_yaml_hien_kem_doc_nguoc_ra_dung_bo_luat(client):
    """Tab YAML dung de doi chieu nguyen van va tai ve lam seed. Parse lai
    phai ra dung tung luat — neu khong no la mot ban dien giai sai."""
    body = client.get("/api/rules", headers=as_user(ADMIN)).json()
    parsed = rules_file.parse(body["raw"])
    assert parsed["version"] == body["version"]
    assert [(r["id"], r["severity"], r["sql"]) for r in parsed["rules"]] == [
        (r["id"], r["severity"], r["sql"].strip()) for r in body["rules"]]


def test_file_seed_da_vao_db_luc_migrate(client):
    """Moi luat trong file seed deu co trong DB sau migration p10 (tru khi
    da bi xoa qua giao dien — test chi chay khi bo luat con nguyen seed)."""
    body = client.get("/api/rules", headers=as_user(ADMIN)).json()
    goc = yaml.safe_load(RULES_YAML.read_text())
    if body["version"] != goc["version"]:
        pytest.skip("bo luat da duoc sua qua giao dien — khong con bang seed")
    assert [r["id"] for r in body["rules"]] == [r["id"] for r in goc["rules"]]


def test_noi_ro_qc_da_chay_duoi_version_nao(client):
    body = client.get("/api/rules", headers=as_user(ADMIN)).json()
    assert "applied_version" in body
    assert body["in_sync"] == (
        body["applied_version"] is not None and body["applied_version"] == body["current_version"])


def test_bo_luat_khong_phai_du_lieu_nen_khong_theo_pham_vi(client):
    """Analyst chi thay bang cua minh, nhung LUAT thi ai cung doc duoc."""
    tx = client.get("/api/rules", headers=as_user(TX))
    admin = client.get("/api/rules", headers=as_user(ADMIN))
    assert tx.status_code == 200
    assert tx.json()["rules"] == admin.json()["rules"]


def test_chi_team_lead_va_admin_thay_nut_sua(client):
    assert client.get("/api/rules", headers=as_user(ADMIN)).json()["can_edit"] is True
    assert client.get("/api/rules", headers=as_user(LEAD)).json()["can_edit"] is True
    assert client.get("/api/rules", headers=as_user(TX)).json()["can_edit"] is False


def test_nguoi_la_khong_vao_duoc(client):
    assert client.get("/api/rules", headers=as_user("nguoi.la@dataops.test")).status_code == 403


def test_version_khong_co_snapshot_thi_404(client):
    assert client.get("/api/rules?version=99999", headers=as_user(ADMIN)).status_code == 404


# ------------------------------------------------------------ phan quyen

def test_analyst_khong_sua_duoc_luat(client, bo_luat):
    assert _tao(client, bo_luat, user=TX).status_code == 403
    assert client.put("/api/rules/deposit_spike", headers=as_user(TX), json={
        "severity": "info", "message": "x", "sql": SQL_OK,
        "expected_version": bo_luat}).status_code == 403
    assert client.delete(f"/api/rules/deposit_spike?expected_version={bo_luat}",
                         headers=as_user(TX)).status_code == 403
    assert client.post("/api/rules/preview", headers=as_user(TX),
                       json={"sql": SQL_OK}).status_code == 403
    assert client.post("/api/rules/run-qc", headers=as_user(TX)).status_code == 403


# ------------------------------------------------- khong luu luat hong

def test_sai_cau_truc_bao_het_loi_mot_luot(client, bo_luat):
    r = client.post("/api/rules", headers=as_user(ADMIN), json={
        "id": "Sai Ten!", "severity": "nghiem trong", "message": "", "sql": SQL_OK,
        "scope": ["texas"], "expected_version": bo_luat})
    assert r.status_code == 422
    loi = r.json()["detail"]["errors"]
    assert any("'id'" in m for m in loi)
    assert any("severity" in m for m in loi)
    assert any("message" in m for m in loi)
    assert any("scope" in m for m in loi)
    assert _catalog()["version"] == bo_luat


def test_sql_thieu_cot_thi_noi_ro_cot_nao(client, bo_luat):
    r = _tao(client, bo_luat, sql="SELECT year, state, institution_id, institution FROM fact_current")
    assert r.status_code == 422
    assert r.json()["detail"]["missing_columns"] == ["observed"]


def test_sql_ghi_du_lieu_bi_chan_boi_transaction_chi_doc(client, bo_luat):
    """Chan bang READ ONLY cua Postgres, khong phai bang danh sach tu khoa.
    nextval() la mot lenh GHI — transaction chi doc tu choi no."""
    sql = ("SELECT 1 AS year, 'TX' AS state, 1 AS institution_id, 'x' AS institution, "
           "NULL::jsonb AS observed FROM (SELECT nextval('audit_log_id_seq')) s")
    r = _tao(client, bo_luat, sql=sql)
    assert r.status_code == 422
    assert "read-only" in json.dumps(r.json()).lower()


@pytest.fixture
def bang_canh_gac():
    """Bang lam bia cho test tan cong. KHONG BAO GIO nham vao bang that:
    ban dau test nay nham vao `ticket`, va khi lop protocol con ho no da
    xoa that bang ticket o database local."""
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS test_p10_canh_gac (x int)")
        c.commit()
    yield "test_p10_canh_gac"
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS test_p10_canh_gac")
        c.commit()


def _con(bang: str) -> bool:
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", (bang,))
        return cur.fetchone()[0]


def test_khong_thoat_duoc_ra_khoi_subquery_qua_api(client, bo_luat, bang_canh_gac):
    sql = f"{SQL_OK}) x; COMMIT; DROP TABLE {bang_canh_gac}; SELECT * FROM ({SQL_OK}"
    r = _tao(client, bo_luat, sql=sql)
    assert r.status_code == 422
    r = client.post("/api/rules/preview", headers=as_user(ADMIN), json={"sql": sql})
    assert r.status_code == 422
    assert _con(bang_canh_gac)


@pytest.mark.parametrize("scope", [None, ["TX"]])
def test_lop_protocol_cung_chan_nhieu_lenh(bang_canh_gac, scope):
    """Lop hai, bo qua validate: dry_run luon truyen tham so nen Postgres
    khong nhan nhieu lenh. Truoc khi sua, nhanh scope=None lot qua."""
    sql = f"{SQL_OK}) x; COMMIT; DROP TABLE {bang_canh_gac}; SELECT * FROM ({SQL_OK}"
    with psycopg.connect(URL, row_factory=dict_row) as conn:
        res = rules_file.dry_run(conn, sql, scope)
    assert res["ok"] is False and res["error"]
    assert _con(bang_canh_gac)


def test_sql_cu_phap_sai_thi_422(client, bo_luat):
    r = _tao(client, bo_luat, sql="SELEC nothing")
    assert r.status_code == 422
    assert r.json()["detail"]["errors"][0].startswith("SQL loi")


# ------------------------------------------------------------- ghi

def test_tao_luat_tang_version_ghi_snapshot_va_audit(client, bo_luat):
    r = _tao(client, bo_luat, scope=["tx", "ca"])
    assert r.status_code == 201, r.text
    assert r.json()["version"] == bo_luat + 1
    assert r.json()["rule"]["scope"] == ["TX", "CA"]

    cat = _catalog()
    assert cat["version"] == bo_luat + 1
    assert cat["rules"][-1]["id"] == "test_p10_a"
    # vua sua xong, QC chua chay -> phai hien la lech
    assert cat["in_sync"] is False

    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("SELECT rules FROM qc_ruleset_snapshot WHERE version = %s", (bo_luat + 1,))
        snap = cur.fetchone()[0]
        cur.execute("""SELECT actor, action FROM audit_log
                       WHERE entity = 'qc_rule' AND entity_key = 'test_p10_a'""")
        audits = cur.fetchall()
    assert "test_p10_a" in [x["id"] for x in snap]
    assert audits == [(ADMIN, "rule_create")]


def test_team_lead_sua_duoc_va_tat_duoc_luat(client, bo_luat):
    assert _tao(client, bo_luat).status_code == 201
    r = client.put("/api/rules/test_p10_a", headers=as_user(LEAD), json={
        "severity": "critical", "message": "da sua", "sql": SQL_OK + ";",
        "enabled": False, "expected_version": bo_luat + 1})
    assert r.status_code == 200, r.text
    rule = r.json()["rule"]
    assert (rule["severity"], rule["enabled"], rule["updated_by"]) == ("critical", False, LEAD)
    # dau ; cuoi bi bo — luat nam trong subquery cua QC Runner
    assert not rule["sql"].endswith(";")


def test_trung_id_thi_409(client, bo_luat):
    assert _tao(client, bo_luat).status_code == 201
    r = _tao(client, bo_luat + 1)
    assert r.status_code == 409


def test_hai_nguoi_sua_cung_luc_nguoi_sau_nhan_409(client, bo_luat):
    assert _tao(client, bo_luat, user=LEAD).status_code == 201
    # nguoi thu hai van dang nhin version cu
    r = _tao(client, bo_luat, rule_id="test_p10_b")
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["current_version"] == bo_luat + 1
    assert d["updated_by"] == LEAD
    assert "test_p10_b" not in [x["id"] for x in _catalog()["rules"]]


def test_xoa_luat_van_con_trong_snapshot_cu(client, bo_luat):
    assert _tao(client, bo_luat).status_code == 201
    r = client.delete(f"/api/rules/test_p10_a?expected_version={bo_luat + 1}",
                      headers=as_user(ADMIN))
    assert r.status_code == 200
    assert r.json()["version"] == bo_luat + 2
    assert "test_p10_a" not in [x["id"] for x in _catalog()["rules"]]

    cu = client.get(f"/api/rules?version={bo_luat + 1}", headers=as_user(ADMIN)).json()
    assert cu["snapshot"] is True and cu["can_edit"] is False
    assert "test_p10_a" in [x["id"] for x in cu["rules"]]


def test_xoa_luat_khong_ton_tai_thi_404(client, bo_luat):
    r = client.delete(f"/api/rules/test_p10_khong_co?expected_version={bo_luat}",
                      headers=as_user(ADMIN))
    assert r.status_code == 404
    assert _catalog()["version"] == bo_luat


# ------------------------------------------------------------ chay thu

def test_chay_thu_tra_cot_so_dong_va_mau(client):
    r = client.post("/api/rules/preview", headers=as_user(LEAD), json={
        "sql": "SELECT year, state, institution_id, institution, "
               "jsonb_build_object('deposit', deposit) AS observed FROM fact_current",
        "scope": ["TX"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["missing_columns"] == []
    assert isinstance(body["count"], int)
    assert len(body["rows"]) <= rules_file.PREVIEW_SAMPLE
    assert all(row["state"] == "TX" for row in body["rows"])


def test_chay_thu_chiu_duoc_dau_phan_tram(client):
    """QC Runner truyen tham so vao SQL cua luat, nen `%` phai duoc nhan
    doi o CA HAI noi. Truoc P10 luat co LIKE 'A%' se lam hong ca job."""
    r = client.post("/api/rules/preview", headers=as_user(ADMIN), json={
        "sql": "SELECT year, state, institution_id, institution, NULL::jsonb AS observed "
               "FROM fact_current WHERE institution LIKE 'A%'", "scope": ["CA"]})
    assert r.status_code == 200
    assert r.json()["ok"] is True, r.json()


def test_chay_thu_co_timeout(client, monkeypatch):
    monkeypatch.setattr(rules_file, "PREVIEW_TIMEOUT_MS", 200)
    r = client.post("/api/rules/preview", headers=as_user(ADMIN), json={
        "sql": "SELECT 1 AS year, 'TX' AS state, 1 AS institution_id, 'x' AS institution, "
               "NULL::jsonb AS observed FROM pg_sleep(2)"})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "timeout" in r.json()["error"].lower()


# -------------------------------------------------------- ky + chay QC

def test_sua_luat_xong_chua_chay_qc_thi_khong_ky_duoc(client, bo_luat):
    """Ky luc nay la ky phieu duyet noi ve vi pham cua bo luat CU."""
    gate = client.get("/api/gate", headers=as_user(LEAD)).json()
    if gate["blocking_tickets"] or gate["qc_stale"]:
        pytest.skip("cong dang khoa vi ly do khac")
    assert _tao(client, bo_luat).status_code == 201

    gate = client.get("/api/gate", headers=as_user(LEAD)).json()
    assert gate["locked"] is True and gate["qc_stale_reason"] == "rules"
    r = client.post("/api/release", headers=as_user(LEAD),
                    json={"label": "[test] p10", "approval_note": "x" * 20})
    assert r.status_code == 409
    assert "bo luat" in json.dumps(r.json())


def test_chay_qc_khong_goi_duoc_job_thi_503(client, monkeypatch):
    from app.main import settings
    monkeypatch.setattr(settings, "gcp_project_id", "")
    assert client.post("/api/rules/run-qc", headers=as_user(LEAD)).status_code == 503


# ------------------------------------------- doc file seed (khong can DB)

def test_thieu_khoa_rules_thi_bao_ro():
    with pytest.raises(ValueError, match="rules"):
        rules_file.parse("version: 1\n")


def test_yaml_hong_thi_bao_ro():
    with pytest.raises(ValueError, match="YAML"):
        rules_file.parse("rules: [\n  - id: a\n")


def test_file_seed_hop_le():
    assert rules_file.validate_catalog(rules_file.parse(RULES_YAML.read_text())["rules"]) == []


def test_duong_dan_nong_trong_image_khong_lam_no_vo(monkeypatch):
    """Trong image API, app/ nam ngay duoi /srv — khong du bon cap cha.
    Migration p10 goi ham nay trong image de tim file seed."""
    monkeypatch.setattr(rules_file, "__file__", "/srv/app/rules.py")
    rules_file.rules_path()  # truoc khi sua: IndexError


def test_khong_co_scope_la_ap_cho_moi_bang():
    parsed = rules_file.parse(
        "version: 1\nrules:\n"
        "  - {id: a, severity: info, message: m, sql: 'SELECT 1'}\n"
        "  - {id: b, severity: info, message: m, sql: 'SELECT 1', scope: [tx]}\n")
    assert parsed["rules"][0]["scope"] is None
    assert parsed["rules"][1]["scope"] == ["TX"]
