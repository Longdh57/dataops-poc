"""Bo luat doc len man hinh phai la CHINH file luat, khong phai ban cheo.

Man hinh "Bo luat" ton tai de nguoi khong mo duoc repo van doi chieu
duoc rule_id tren bang vi pham voi luat that. Neu API bay ra mot ban
khac file, ca muc dich cua no mat — nen test o day bam vao dung diem do:
danh sach tra ve phai khop tung id voi rules/rules.yaml.
"""

from pathlib import Path

import pytest
import yaml
from conftest import ADMIN, TX, as_user

from app import rules as rules_file

RULES_YAML = Path(__file__).resolve().parents[3] / "rules" / "rules.yaml"


def _file_rules() -> dict:
    return yaml.safe_load(RULES_YAML.read_text())


# ------------------------------------------------------------- endpoint

def test_tra_ve_dung_bo_luat_trong_file(client):
    res = client.get("/api/rules", headers=as_user(ADMIN))
    assert res.status_code == 200, res.text
    body = res.json()

    goc = _file_rules()
    assert body["version"] == goc["version"]
    assert [r["id"] for r in body["rules"]] == [r["id"] for r in goc["rules"]]
    assert body["source"] == "rules/rules.yaml"


def test_kem_noi_dung_tho_de_doi_chieu(client):
    """Ban dien giai co the sai; file thi khong. Giao dien phai xem duoc ca hai."""
    body = client.get("/api/rules", headers=as_user(ADMIN)).json()
    assert body["raw"] == RULES_YAML.read_text()


def test_noi_ro_qc_da_chay_duoi_version_nao(client):
    """Version trong file va version QC da chay la HAI so khac nhau.

    Gop lam mot thi nguoi doc se doi chieu danh sach vi pham voi mot bo
    luat chua tung chay — dung luc nguy hiem nhat: vua sua luat xong.
    """
    body = client.get("/api/rules", headers=as_user(ADMIN)).json()
    assert "applied_version" in body
    assert body["in_sync"] == (
        body["applied_version"] is not None and body["applied_version"] == body["version"])


def test_bo_luat_khong_phai_du_lieu_nen_khong_theo_pham_vi(client):
    """Analyst chi thay bang cua minh, nhung LUAT thi ai cung doc duoc —
    no la quy tac chung, khong phai so lieu."""
    tx = client.get("/api/rules", headers=as_user(TX))
    admin = client.get("/api/rules", headers=as_user(ADMIN))
    assert tx.status_code == 200
    assert tx.json()["rules"] == admin.json()["rules"]


def test_nguoi_la_khong_vao_duoc(client):
    res = client.get("/api/rules", headers=as_user("nguoi.la@dataops.test"))
    assert res.status_code == 403


# ------------------------------------------- doc file (khong can database)

def test_thieu_khoa_rules_thi_bao_ro():
    with pytest.raises(ValueError, match="rules"):
        rules_file.parse("version: 1\n")


def test_yaml_hong_thi_bao_ro():
    with pytest.raises(ValueError, match="YAML"):
        rules_file.parse("rules: [\n  - id: a\n")


def test_duong_dan_nong_trong_image_khong_lam_no_vo(monkeypatch):
    """Trong image API, app/ nam ngay duoi /srv — khong du bon cap cha.

    Ban dau ham dung thang parents[3] nen no IndexError ngay khi dung danh
    sach duong dan, truoc ca khi kip thu /srv/rules/rules.yaml — endpoint
    chet hoan toan trong container du file luat nam san o do. Test chay tu
    source nen khong bat duoc, phai gia lap duong dan nong.
    """
    monkeypatch.setattr(rules_file, "__file__", "/srv/app/rules.py")
    rules_file.rules_path()  # truoc khi sua: IndexError


def test_khong_co_scope_la_ap_cho_moi_bang():
    parsed = rules_file.parse(
        "version: 1\nrules:\n"
        "  - {id: a, severity: info, message: m, sql: 'SELECT 1'}\n"
        "  - {id: b, severity: info, message: m, sql: 'SELECT 1', scope: [tx]}\n")
    assert parsed["rules"][0]["scope"] is None
    # Viet thuong trong file van ra dung ma bang — QC Runner cung upper().
    assert parsed["rules"][1]["scope"] == ["TX"]
