"""Dong bang du lieu BigQuery luc ky — moi ban ky mot table snapshot.

Truoc day ban ky chi giu DANH SACH run_id, con Export Job doc thang bang
fact dang song. Team Data sua so tai cho duoi cung mot run_id la chuyen
binh thuong, nen file gui khach co the mang so chua ai duyet trong khi
van dong dau "ban da ky". Snapshot giai quyet tan goc: file luon doc tu
mot ban chup chi-doc, tao dung luc ky.

Ba quyet dinh (chi tiet trong docs/thiet-ke-ky-du-lieu.md):

- Ten `snapshot_<epoch giay luc ky>`, nam o dataset RIENG
  (`settings.bigquery_signed_dataset`) — ung dung ghi duoc o do, team
  Data thi khong, va dataset nguon van giu nguyen tac "ung dung chi doc".
- Snapshot BigQuery chi tinh tien phan du lieu bang goc thay doi ve sau,
  nen chup ca bang ma khong loc; Export van loc theo source_run_ids.
- Chup xong phai DOI CHIEU van tay voi ban sao Postgres ma QC da kiem.
  Lech nghia la nguon da doi sau lan dong bo cuoi — ky luc do la ky mot
  thu QC chua nhin thay, nen xoa snapshot va tu choi.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from .settings import settings


class SnapshotError(Exception):
    """Khong dong bang duoc. `status` la ma HTTP endpoint ky nen tra ve."""

    def __init__(self, status: int, detail):
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def table_name(signed_at: datetime) -> str:
    return f"snapshot_{int(signed_at.timestamp())}"


def _client():
    from google.cloud import bigquery
    return bigquery.Client(project=settings.gcp_project_id)


def _source_id() -> str:
    return f"{settings.gcp_project_id}.{settings.bigquery_dataset}.{settings.bigquery_table}"


def bq_checksum(bq, table_id: str, run_ids: list[str]) -> str:
    """Cung cong thuc voi `data_checksum` ben Postgres, tinh tren BigQuery.

    Postgres lay 8 ky tu hex dau cua md5 roi ep ve int 32 bit CO DAU
    (`::bit(32)::int`). BigQuery doc hex thanh so khong dau, nen phai tru
    2^32 cho nua tren de ra dung cung mot so.
    """
    from google.cloud import bigquery

    sql = f"""
        WITH h AS (
          SELECT deposit,
                 CAST(CONCAT('0x', SUBSTR(TO_HEX(MD5(CONCAT(
                     CAST(year AS STRING), '|', state, '|',
                     CAST(institution_id AS STRING), '|', CAST(deposit AS STRING)
                 ))), 1, 8)) AS INT64) AS u
          FROM `{table_id}`
          WHERE run_id IN UNNEST(@runs)
        )
        SELECT COUNT(*) AS n, COALESCE(SUM(deposit), 0) AS total,
               COALESCE(SUM(IF(u >= 2147483648, u - 4294967296, u)), 0) AS h
        FROM h
    """
    cfg = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("runs", "STRING", run_ids)])
    r = next(iter(bq.query(sql, location=settings.region, job_config=cfg).result()))
    return hashlib.md5(f"{r['n']}:{r['total']}:{r['h']}".encode()).hexdigest()


def drop(table_id: str) -> None:
    """Xoa snapshot mo coi (ky that bai sau khi da chup). Khong nem loi."""
    try:
        _client().delete_table(table_id, not_found_ok=True)
    except Exception:  # noqa: BLE001 — don dep, khong duoc che loi goc
        pass


def freeze(signed_at: datetime, run_ids: list[str], expected_checksum: str | None,
           label: str, signed_by: str) -> str:
    """Chup bang fact thanh snapshot, doi chieu van tay, tra ve table id day du.

    Nem SnapshotError khi khong chup duoc hoac du lieu da lech voi ban QC
    da kiem — luc do snapshot (neu da tao) bi xoa ngay.
    """
    if not settings.gcp_project_id:
        raise SnapshotError(503, "khong co GCP_PROJECT_ID — khong tao duoc snapshot BigQuery "
                                 "nen khong ky duoc")

    from google.api_core.exceptions import Conflict
    from google.cloud import bigquery

    bq = _client()
    dest = f"{settings.gcp_project_id}.{settings.bigquery_signed_dataset}.{table_name(signed_at)}"

    # Copy job kieu SNAPSHOT thay vi DDL: khong phai ghep ten bang vao chuoi
    # SQL, va WRITE_EMPTY dam bao khong bao gio ghi de mot ban ky khac.
    cfg = bigquery.CopyJobConfig(operation_type="SNAPSHOT",
                                 write_disposition="WRITE_EMPTY")
    try:
        bq.copy_table(_source_id(), dest, job_config=cfg, location=settings.region).result()
    except Conflict:
        raise SnapshotError(409, f"snapshot {dest} da ton tai — co nguoi vua ky cung giay nay, "
                                 "thu lai sau vai giay")
    except Exception as exc:  # noqa: BLE001
        raise SnapshotError(503, f"khong tao duoc snapshot BigQuery: {exc}")

    try:
        table = bq.get_table(dest)
        table.description = (f"Ban ky '{label}' — {signed_by} — {signed_at.isoformat()}. "
                             "Export doc tu day; KHONG xoa khi ban ky con duoc dung.")
        table.labels = {"app": "dataops", "kind": "signed-version"}
        bq.update_table(table, ["description", "labels"])

        actual = bq_checksum(bq, dest, run_ids)
    except Exception as exc:  # noqa: BLE001
        drop(dest)
        raise SnapshotError(503, f"khong doi chieu duoc snapshot {dest}: {exc}")

    if expected_checksum and actual != expected_checksum:
        drop(dest)
        raise SnapshotError(409, {
            "loi": "BigQuery da doi so voi ban QC da kiem",
            "van_tay_qc_da_kiem": expected_checksum,
            "van_tay_bigquery_luc_ky": actual,
            "y_nghia": "team Data vua sua nguon sau lan dong bo cuoi — cho Sync va QC "
                       "chay lai tren so moi roi ky",
        })
    return dest
