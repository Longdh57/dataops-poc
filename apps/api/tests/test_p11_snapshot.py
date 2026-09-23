"""P11: ky la dong bang ca DU LIEU, khong chi danh sach run_id.

Ba dieu giu o day: ban ky luon ghi ten snapshot va ten do khop voi thoi
diem ky; khong chup duoc snapshot thi khong co ban ky nao ca; va ban ky
khong co snapshot thi khong xuat duoc file tu bang dang song.
"""

from datetime import datetime, timezone

import psycopg
import pytest
from conftest import ADMIN, LEAD, as_user

from app import bq_snapshot

URL = "postgresql://dataops:dataops@localhost:5432/dataops"
NHAN = "[test-p11]"
PHIEU = "ban kiem thu tu dong, khong gui khach"


@pytest.fixture(autouse=True)
def don_dep():
    yield
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("""DELETE FROM export_job WHERE signed_version_id IN
                         (SELECT id FROM signed_version WHERE label LIKE %s)""", (f"{NHAN}%",))
        cur.execute("DELETE FROM signed_version WHERE label LIKE %s", (f"{NHAN}%",))
        c.commit()


def _gate_mo(client) -> bool:
    return not client.get("/api/gate", headers=as_user(ADMIN)).json()["locked"]


def _row(sql: str, args=()):
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone()


def test_ten_snapshot_theo_epoch_giay_luc_ky():
    luc = datetime(2024, 10, 6, 8, 31, 34, tzinfo=timezone.utc)
    assert bq_snapshot.table_name(luc) == "snapshot_1728203494"


def test_ky_ghi_ten_snapshot_khop_thoi_diem_ky(client, monkeypatch):
    if not _gate_mo(client):
        pytest.skip("cong dang khoa, khong ky duoc")

    goi = {}

    def freeze(signed_at, run_ids, expected_checksum, label, signed_by):
        goi.update(signed_at=signed_at, run_ids=run_ids, checksum=expected_checksum)
        return f"test-project.dataops_signed.{bq_snapshot.table_name(signed_at)}"

    monkeypatch.setattr(bq_snapshot, "freeze", freeze)
    r = client.post("/api/release", json={"label": f"{NHAN} co snapshot", "approval_note": PHIEU},
                    headers=as_user(LEAD))
    assert r.status_code == 200, r.text
    body = r.json()

    snap, signed_at = _row("SELECT bq_snapshot, signed_at FROM signed_version WHERE id = %s",
                           (body["id"],))
    assert snap == body["bq_snapshot"]
    # Ten bang va signed_at phai chi cung mot khoanh khac.
    assert snap.endswith(f".snapshot_{int(signed_at.timestamp())}")
    # Doi chieu snapshot voi dung van tay va dung lan nap ma ban ky ghi lai.
    assert goi["checksum"] == body["checksum"]
    assert goi["run_ids"] == body["source_run_ids"]


def test_khong_chup_duoc_snapshot_thi_khong_co_ban_ky(client, monkeypatch):
    if not _gate_mo(client):
        pytest.skip("cong dang khoa, khong ky duoc")

    def freeze(*a, **kw):
        raise bq_snapshot.SnapshotError(409, {"loi": "BigQuery da doi so voi ban QC da kiem"})

    monkeypatch.setattr(bq_snapshot, "freeze", freeze)
    r = client.post("/api/release", json={"label": f"{NHAN} lech so", "approval_note": PHIEU},
                    headers=as_user(LEAD))
    assert r.status_code == 409
    assert _row("SELECT count(*) FROM signed_version WHERE label = %s",
                (f"{NHAN} lech so",))[0] == 0


def test_ban_ky_khong_co_snapshot_thi_khong_xuat_file(client):
    if not _gate_mo(client):
        pytest.skip("cong dang khoa")
    with psycopg.connect(URL) as c, c.cursor() as cur:
        cur.execute("""INSERT INTO signed_version
                           (run_id, source_run_ids, label, row_count, signed_by)
                       VALUES ('run-cu', '["run-A"]', %s, 1, %s)""",
                    (f"{NHAN} ky truoc P11", LEAD))
        c.commit()

    r = client.post("/api/exports", json={"format": "csv"}, headers=as_user(ADMIN))
    assert r.status_code == 409
    assert "snapshot" in r.text
