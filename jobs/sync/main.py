"""Sync Job — BigQuery -> Cloud SQL.

Luong:
  1. Doc dau van tay cua nguon tu __TABLES__ (metadata, KHONG quet du lieu
     nen khong tinh phi). So voi sync_state; khong doi thi dung ngay.
  2. EXPORT DATA ra parquet tren GCS — BigQuery ghi song song, ung dung
     khong bao gio giu du lieu trong bo nho.
  3. COPY vao bang staging.
  4. Doi ten trong mot transaction — khong downtime, khong co khoanh khac
     nao bang bi trong.

Chay duoc ca local (docker compose) lan tren Cloud Run Jobs.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

import psycopg
import pyarrow.parquet as pq
from google.cloud import bigquery, storage

PROJECT = os.getenv("GCP_PROJECT_ID", "dataops-poc-2026")
DATASET = os.getenv("BQ_DATASET", "dataops_src")
TABLE = os.getenv("BQ_TABLE", "fact_names")
BUCKET = os.getenv("STAGING_BUCKET", f"{PROJECT}-staging")
LOCATION = os.getenv("BQ_LOCATION", "asia-southeast1")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dataops:dataops@localhost:5432/dataops")

COLUMNS = ["run_id", "year", "state", "institution_id", "institution", "deposit",
           "deposit_share", "prev_deposit", "prev_year"]


def log(msg: str) -> None:
    print(f"[sync] {msg}", flush=True)


# ---------------------------------------------------------------- phat hien

def source_fingerprint(bq: bigquery.Client) -> tuple[datetime, int]:
    """Doc last_modified_time va row_count tu __TABLES__.

    Day la truy van METADATA: khong quet du lieu bang, khong tinh phi.
    Nho vay poll moi 60 giay ca ngay van khong ton dong nao.
    """
    sql = f"""
        SELECT last_modified_time, row_count
        FROM `{PROJECT}.{DATASET}.__TABLES__`
        WHERE table_id = @t
    """
    job = bq.query(
        sql,
        location=LOCATION,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("t", "STRING", TABLE)]
        ),
    )
    rows = list(job.result())
    if not rows:
        raise RuntimeError(f"Khong tim thay bang {TABLE} trong {DATASET}")

    log(f"metadata query quet {job.total_bytes_processed or 0} byte")
    r = rows[0]
    return datetime.fromtimestamp(r.last_modified_time / 1000, tz=timezone.utc), r.row_count


def read_sync_state(conn: psycopg.Connection) -> tuple[datetime | None, int | None]:
    with conn.cursor() as cur:
        cur.execute("SELECT source_last_modified, source_row_count FROM sync_state WHERE id = 1")
        row = cur.fetchone()
    return (row[0], row[1]) if row else (None, None)


# ------------------------------------------------------------------- xuat

def export_to_gcs(bq: bigquery.Client, run_id: str) -> str:
    prefix = f"sync/{run_id}"
    uri = f"gs://{BUCKET}/{prefix}/part-*.parquet"
    sql = f"""
        EXPORT DATA OPTIONS(uri='{uri}', format='PARQUET', overwrite=true) AS
        SELECT {', '.join(COLUMNS)}
        FROM `{PROJECT}.{DATASET}.{TABLE}`
    """
    job = bq.query(sql, location=LOCATION)
    job.result()
    log(f"EXPORT DATA xong -> {uri}")
    return prefix


# ------------------------------------------------------------------- nap

def load_into_staging(conn: psycopg.Connection, prefix: str, workdir: str) -> int:
    gcs = storage.Client(project=PROJECT)
    blobs = [b for b in gcs.list_blobs(BUCKET, prefix=prefix) if b.name.endswith(".parquet")]
    if not blobs:
        raise RuntimeError(f"Khong co file parquet nao o {prefix}")
    log(f"{len(blobs)} file parquet can nap")

    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS fact_staging")
        # CHI copy cau truc cot, KHONG copy index. Hai ly do:
        #  - COPY vao bang khong index nhanh hon han
        #  - ten index do minh dat, khong bi Postgres tu sinh roi troi dan
        cur.execute("CREATE TABLE fact_staging (LIKE fact_current INCLUDING DEFAULTS)")
    conn.commit()

    total = 0
    copy_sql = f"COPY fact_staging ({', '.join(COLUMNS)}) FROM STDIN"

    with conn.cursor() as cur:
        # Bang staging la du lieu dung mot lan, hong thi sync lai tu BigQuery.
        # Khong can cho fsync WAL sau moi commit.
        cur.execute("SET synchronous_commit = off")
    conn.commit()

    for blob in blobs:
        local = os.path.join(workdir, os.path.basename(blob.name))
        blob.download_to_filename(local)
        table = pq.read_table(local, columns=COLUMNS)

        with conn.cursor() as cur, cur.copy(copy_sql) as copy:
            for batch in table.to_batches(max_chunksize=10_000):
                cols = [batch.column(c).to_pylist() for c in COLUMNS]
                for row in zip(*cols):
                    copy.write_row(row)
                total += batch.num_rows
        conn.commit()
        os.remove(local)
        log(f"  {blob.name}: cong don {total:,} dong")

    return total


# Ten index chuan + dinh nghia. Tao sau khi COPY xong.
INDEXES = {
    "fact_pkey":            "(year, state, institution_id)",
    "ix_fact_filter_sort":  "(state, year, deposit DESC)",
    "ix_fact_institution":  "(institution)",
}


def build_indexes(conn: psycopg.Connection) -> None:
    """Tao index tren bang staging voi ten tam, doi ten chuan sau khi swap."""
    with conn.cursor() as cur:
        # Mac dinh cua db-f1-micro qua nho, sap xep khi build index tran ra
        # dia (PD_HDD) — chiem gan 90% thoi gian sync. Nang len trong pham vi
        # RAM cua may de sap xep trong bo nho.
        cur.execute("SET maintenance_work_mem = '160MB'")
        cur.execute("SET synchronous_commit = off")
        cur.execute(f"ALTER TABLE fact_staging ADD CONSTRAINT fact_pkey_tmp "
                    f"PRIMARY KEY {INDEXES['fact_pkey']}")
        for name, cols in INDEXES.items():
            if name == "fact_pkey":
                continue
            cur.execute(f"CREATE INDEX {name}_tmp ON fact_staging {cols}")
    conn.commit()
    log(f"tao {len(INDEXES)} index xong")


def atomic_swap(conn: psycopg.Connection) -> None:
    """Doi ten trong MOT transaction.

    Request dang chay se thay bang cu cho toi khi COMMIT, roi thay bang moi.
    Khong co khoanh khac nao bang bi thieu.
    """
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS fact_old")
        cur.execute("ALTER TABLE fact_current RENAME TO fact_old")
        cur.execute("ALTER TABLE fact_staging RENAME TO fact_current")
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS fact_old")
        # Bang cu da bien mat -> ten chuan duoc giai phong, doi lai cho gon.
        for name in INDEXES:
            cur.execute(f"ALTER INDEX {name}_tmp RENAME TO {name}")
    conn.commit()
    log("doi ten nguyen tu xong")


def source_run_ids(conn: psycopg.Connection) -> list[str]:
    """Nhung lan nap du lieu (run_id do team Data dat) dang co trong ban sao.

    Doc tu Postgres chu khong tu BigQuery: sau khi swap, bang fact_current
    CHINH LA thu vua nap, nen day la cau tra loi chinh xac va ton 0 dong
    chi phi query. Ky phat hanh se dong bang danh sach nay, va Export Job
    loc theo no de file gui khach khong dinh lan nap chua ai duyet.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT run_id FROM fact_current ORDER BY run_id")
        return [r[0] for r in cur.fetchall()]


def write_sync_state(conn: psycopg.Connection, run_id: str, rows: int,
                     src_mod: datetime, src_rows: int, status: str = "ok",
                     error: str | None = None,
                     data_run_ids: list[str] | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sync_state
                (id, last_run_id, last_synced_at, last_row_count,
                 source_last_modified, source_row_count, status, last_error,
                 source_run_ids)
            VALUES (1, %s, now(), %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                last_run_id = EXCLUDED.last_run_id,
                last_synced_at = EXCLUDED.last_synced_at,
                last_row_count = EXCLUDED.last_row_count,
                source_last_modified = EXCLUDED.source_last_modified,
                source_row_count = EXCLUDED.source_row_count,
                status = EXCLUDED.status,
                last_error = EXCLUDED.last_error,
                source_run_ids = COALESCE(EXCLUDED.source_run_ids, sync_state.source_run_ids)
            """,
            (run_id, rows, src_mod, src_rows, status, error,
             json.dumps(data_run_ids) if data_run_ids is not None else None),
        )
    conn.commit()


# ------------------------------------------------------------------ main

def main() -> int:
    started = time.monotonic()
    bq = bigquery.Client(project=PROJECT)

    with psycopg.connect(DATABASE_URL) as conn:
        src_mod, src_rows = source_fingerprint(bq)
        seen_mod, seen_rows = read_sync_state(conn)

        log(f"nguon : {src_mod.isoformat()} · {src_rows:,} dong")
        log(f"da nap: {seen_mod.isoformat() if seen_mod else '(chua bao gio)'} · "
            f"{f'{seen_rows:,}' if seen_rows else '-'} dong")

        if seen_mod is not None and seen_mod >= src_mod and seen_rows == src_rows:
            log("nguon khong doi — bo qua, khong ton chi phi")
            return 0

        run_id = f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
        log(f"phat hien thay doi -> bat dau nap, run_id={run_id}")

        workdir = os.getenv("WORKDIR", "/tmp/dataops-sync")
        os.makedirs(workdir, exist_ok=True)

        try:
            prefix = export_to_gcs(bq, run_id)
            rows = load_into_staging(conn, prefix, workdir)
            build_indexes(conn)

            if rows != src_rows:
                raise RuntimeError(f"So dong lech: nap {rows:,} nhung nguon co {src_rows:,}")

            atomic_swap(conn)
            data_runs = source_run_ids(conn)
            write_sync_state(conn, run_id, rows, src_mod, src_rows, "ok",
                             data_run_ids=data_runs)
            log(f"ban sao dang giu {len(data_runs)} lan nap: {', '.join(data_runs)}")
            log(f"XONG · {rows:,} dong · {time.monotonic() - started:.1f}s")
            return 0
        except Exception as exc:  # noqa: BLE001
            log(f"LOI: {exc}")
            # Connection dang o trang thai abort — phai rollback truoc
            # khi ghi duoc bat cu thu gi, neu khong se nuot mat loi that.
            conn.rollback()
            write_sync_state(conn, run_id, 0, src_mod, src_rows, "error", str(exc))
            return 1


if __name__ == "__main__":
    sys.exit(main())
