"""Bo luat la thu duoc sua nhieu nhat, boi nguoi khong doc code.

Nen hai thu phai chac: file sai thi bao ro va bao het, va `scope` phai
that su thu hep pham vi chu khong am tham bi bo qua.
"""

from pathlib import Path

import yaml
from conftest import qc_main

ROOT = Path(__file__).resolve().parents[2]
scope_filter = qc_main.scope_filter
validate = qc_main.validate


def luat(**kw):
    base = {"id": "x", "severity": "critical", "message": "m", "sql": "SELECT 1"}
    base.update(kw)
    return base


def test_file_luat_that_phai_hop_le():
    config = yaml.safe_load((ROOT / "rules" / "rules.yaml").read_text())
    assert validate(config["rules"]) == []


def test_bao_het_loi_mot_luot_chu_khong_dung_o_loi_dau():
    loi = validate([
        luat(id=None),
        luat(id="a", severity="nghiem trong"),
        luat(id="b", message=""),
        luat(id="c", sql=""),
    ])
    assert len(loi) == 4
    assert any("thieu 'id'" in m for m in loi)
    assert any("severity" in m for m in loi)


def test_trung_id_bi_bat():
    loi = validate([luat(id="a"), luat(id="a")])
    assert any("trung 'id'" in m for m in loi)


def test_scope_rong_hoac_sai_kieu_bi_bat():
    assert any("scope" in m for m in validate([luat(scope=[])]))
    assert any("scope" in m for m in validate([luat(scope="CA")]))
    assert validate([luat(scope=["CA", "TX"])]) == []


def test_khong_co_scope_thi_khong_them_dieu_kien():
    assert scope_filter(luat()) == ("", [])


def test_co_scope_thi_loc_theo_bang_va_khong_phan_biet_hoa_thuong():
    where, params = scope_filter(luat(scope=["ca", "Tx"]))
    assert where == "WHERE x.state = ANY(%s)"
    assert params == [["CA", "TX"]]
