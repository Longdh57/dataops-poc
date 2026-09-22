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


# ---------------------------------------------- day len BigQuery (P7)

rows_for_bq = qc_main.qc_exception_rows_for_bigquery


def test_datetime_thanh_iso_con_observed_giu_nguyen_object():
    import datetime as dt

    rows = [{
        "id": 1, "run_id": "run-1", "rule_id": "tang_dot_bien", "severity": "critical",
        "year": 2013, "state": "TX", "institution_id": 3510, "institution": "Bank of America",
        "message": "m", "observed": {"deposit": 98, "prev_deposit": 6},
        "created_at": dt.datetime(2026, 9, 22, 2, 30, tzinfo=dt.timezone.utc),
    }]
    out = rows_for_bq(rows, synced_at="2026-09-22T03:00:00+00:00")
    assert out[0]["created_at"] == "2026-09-22T02:30:00+00:00"
    assert out[0]["observed"] == {"deposit": 98, "prev_deposit": 6}
    assert out[0]["synced_at"] == "2026-09-22T03:00:00+00:00"


def test_created_at_rong_thanh_none_khong_nem_loi():
    rows = [{
        "id": 1, "run_id": "run-1", "rule_id": "r", "severity": "warning",
        "year": None, "state": None, "institution_id": None, "institution": None,
        "message": "m", "observed": None, "created_at": None,
    }]
    out = rows_for_bq(rows, synced_at="2026-09-22T03:00:00+00:00")
    assert out[0]["created_at"] is None
    assert out[0]["observed"] is None
