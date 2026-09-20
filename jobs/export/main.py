"""Export Job — sinh file deliverable tu ban da ky.

Bon rang buoc quyet dinh noi dung file, theo dung thu tu quan trong:

1. CHI lay nhung lan nap nam trong ban da ky. `signed_version.source_run_ids`
   dong bang danh sach nay luc ky. Khong co no thi file se dinh ca lan nap
   den sau khi ky — du lieu chua ai duyet di thang ra ngoai.
2. CHI lay nhung bang trong pham vi nguoi xin. Pham vi duoc chot luc xin
   file, khong phai luc job chay.
3. Ap override cua nguoi dung len so goc, VA tinh lai thi phan cho nhom co
   override — neu khong, khach cong thi phan lai se khong ra 100%.
4. Excel khong chua qua 1.048.576 dong mot sheet. Vuot thi tach sheet va
   ghi canh bao, khong lang le cat mat du lieu.

Doc THANG BigQuery chu khong qua ban sao Postgres: so gui khach phai den
tu nguon su that, khong phu thuoc Sync Job co tre hay khong.

Vi sao khong dung EXPORT DATA de BigQuery ghi thang ra GCS: no khong ap
duoc override nam trong Postgres, khong sinh duoc xlsx, va no chia file
thanh nhieu manh. Doi lai, job nay ghi ra file tam tren dia roi upload —
khong giu ca file trong bo nho.
"""

from __future__ import annotations

import csv
import os
import sys
import tempfile

import psycopg
from google.cloud import bigquery, storage

PROJECT = os.getenv("GCP_PROJECT_ID", "dataops-poc-2026")
DATASET = os.getenv("BQ_DATASET", "dataops_src")
TABLE = os.getenv("BQ_TABLE", "fact_names")
BUCKET = os.getenv("STAGING_BUCKET", f"{PROJECT}-staging")
LOCATION = os.getenv("BQ_LOCATION", "asia-southeast1")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dataops:dataops@localhost:5432/dataops")
JOB_ID = os.getenv("EXPORT_JOB_ID")  # rong = xu ly moi job dang pending

# Gioi han cung cua dinh dang xlsx: 1.048.576 dong ke ca dong tieu de.
EXCEL_MAX_ROWS = 1_048_576

# So chu so thap phan cua thi phan. Mot nhom co the co vai nghin ten, nen
# lam tron cang tho thi cong lai cang lech khoi 100%: o 8 chu so, mot nhom
# 2.000 ten lech toi ~1e-6. O 10 chu so, lech xuong muc khong ai nhin thay.
SHARE_DIGITS = 10
HEADER = ["year", "state", "gender", "name", "number", "market_share", "da_sua"]


def log(m: str) -> None:
    print(f"[export] {m}", flush=True)


# ---------------------------------------------------------------- doc DB

def pending_jobs(conn) -> list[dict]:
    with conn.cursor() as cur:
        base = """SELECT e.id, e.format, e.scope_states, e.requested_by,
                         e.signed_version_id, v.label, v.source_run_ids, v.run_id
                  FROM export_job e
                  LEFT JOIN signed_version v ON v.id = e.signed_version_id
                  WHERE e.status = 'pending'"""
        if JOB_ID:
            cur.execute(f"{base} AND e.id = %s", (JOB_ID,))
        else:
            cur.execute(f"{base} ORDER BY e.id LIMIT 5")
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def overrides(conn) -> dict[tuple, int]:
    with conn.cursor() as cur:
        cur.execute("""SELECT year, state, gender, name, new_value
                       FROM fact_override WHERE field = 'number'""")
        return {(r[0], r[1], r[2], r[3]): int(r[4]) for r in cur.fetchall()}


def gate_locked(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("""SELECT count(*) FROM qc_exception
                       WHERE status='open' AND severity='critical'""")
        return cur.fetchone()[0]


# --------------------------------------------------------------- doc BQ

def fetch_rows(bq: bigquery.Client, run_ids: list[str], states: list[str] | None):
    """Doc BigQuery theo dung ban ky va dung pham vi.

    ORDER BY dat state, year, gender len truoc co hai tac dung: file doc
    de, va cac dong cung mot nhom thi phan nam lien nhau — nho do tinh lai
    thi phan chi can giu MOT nhom trong bo nho.
    """
    where = ["run_id IN UNNEST(@runs)"]
    params = [bigquery.ArrayQueryParameter("runs", "STRING", run_ids)]
    if states:
        where.append("state IN UNNEST(@states)")
        params.append(bigquery.ArrayQueryParameter("states", "STRING", states))

    sql = f"""
        SELECT year, state, gender, name, number, market_share
        FROM `{PROJECT}.{DATASET}.{TABLE}`
        WHERE {' AND '.join(where)}
        ORDER BY state, year, gender, number DESC
    """
    cfg = bigquery.QueryJobConfig(query_parameters=params)
    return bq.query(sql, location=LOCATION, job_config=cfg).result()


def apply_group(group: list[dict], ov: dict[tuple, int]) -> list[list]:
    """Ap override cho mot nhom (year, state, gender) va tinh lai thi phan.

    Chi tinh lai khi nhom that su co override: giu nguyen so cua nguon la
    cach an toan nhat de file khop voi BigQuery o nhung cho khong ai dong toi.
    """
    touched = False
    for r in group:
        fixed = ov.get((r["year"], r["state"], r["gender"], r["name"]))
        if fixed is not None:
            r["number"] = fixed
            r["da_sua"] = "x"
            touched = True

    if touched:
        total = sum(r["number"] for r in group)
        for r in group:
            r["market_share"] = (r["number"] / total) if total else None

    return [[r["year"], r["state"], r["gender"], r["name"], r["number"],
             f"{r['market_share']:.{SHARE_DIGITS}f}" if r["market_share"] is not None else "",
             r["da_sua"]] for r in group]


def stream_groups(rows, ov: dict[tuple, int]):
    """Gom tung nhom thi phan roi nha ra. Bo nho chi giu mot nhom."""
    group: list[dict] = []
    key = None
    for row in rows:
        k = (row.year, row.state, row.gender)
        if key is not None and k != key:
            yield from apply_group(group, ov)
            group = []
        key = k
        group.append({"year": row.year, "state": row.state, "gender": row.gender,
                      "name": row.name, "number": row.number,
                      "market_share": row.market_share, "da_sua": ""})
    if group:
        yield from apply_group(group, ov)


# ------------------------------------------------------------- ghi file

def write_csv(path: str, rows) -> tuple[int, str | None]:
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for row in rows:
            w.writerow(row)
            n += 1
    return n, None


def write_xlsx(path: str, rows) -> tuple[int, str | None]:
    """Ghi xlsx o che do write_only — khong dung ca bang trong bo nho.

    Vuot gioi han mot sheet thi mo sheet tiep chu khong cat bot dong, va
    tra ve canh bao de giao dien noi ro voi nguoi tai file.
    """
    from openpyxl import Workbook

    wb = Workbook(write_only=True)
    sheet = wb.create_sheet("Trang 1")
    sheet.append(HEADER)

    n = 0
    in_sheet = 1  # da co dong tieu de
    sheets = 1
    for row in rows:
        if in_sheet >= EXCEL_MAX_ROWS:
            sheets += 1
            sheet = wb.create_sheet(f"Trang {sheets}")
            sheet.append(HEADER)
            in_sheet = 1
        sheet.append(row)
        in_sheet += 1
        n += 1

    wb.save(path)
    if sheets > 1:
        return n, (f"{n:,} dong vuot gioi han {EXCEL_MAX_ROWS:,} dong mot sheet cua Excel — "
                   f"da tach thanh {sheets} sheet. Can mot file moi sheet thi xuat CSV, "
                   f"hoac loc bot pham vi truoc khi xin file.")
    return n, None


# ------------------------------------------------------------------ main

def process(conn, bq, bucket, job: dict, ov: dict) -> None:
    jid = job["id"]
    if not job["signed_version_id"] or not job["source_run_ids"]:
        raise RuntimeError("job khong gan voi ban ky nao co danh sach lan nap")

    # Cong co the vua khoa lai sau luc xin file. File da sinh ra roi thi
    # kho thu hoi, nen kiem lai ngay truoc khi ghi.
    blocking = gate_locked(conn)
    if blocking:
        raise RuntimeError(f"cong phat hanh dang khoa ({blocking} ngoai le nghiem trong)")

    fmt = job["format"]
    states = job["scope_states"]
    log(f"  job {jid}: ban ky '{job['label']}' · {len(job['source_run_ids'])} lan nap "
        f"· pham vi {states or 'tat ca'} · {fmt}")

    rows = stream_groups(fetch_rows(bq, job["source_run_ids"], states), ov)
    suffix = ".xlsx" if fmt == "xlsx" else ".csv"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        local = tmp.name
    try:
        n, warning = (write_xlsx if fmt == "xlsx" else write_csv)(local, rows)
        path = f"exports/{job['run_id']}/deliverable-{jid}{suffix}"
        bucket.blob(path).upload_from_filename(local)
    finally:
        os.remove(local)

    log(f"  job {jid}: {n:,} dong -> gs://{BUCKET}/{path}")
    if warning:
        log(f"  job {jid}: CANH BAO {warning}")

    with conn.cursor() as cur:
        cur.execute(
            """UPDATE export_job SET status='done', finished_at=now(), gcs_path=%s,
                      row_count=%s, warning=%s
               WHERE id=%s""",
            (f"gs://{BUCKET}/{path}", n, warning, jid))
    conn.commit()


def main() -> int:
    with psycopg.connect(DATABASE_URL) as conn:
        jobs = pending_jobs(conn)
        if not jobs:
            log("khong co job nao dang cho")
            return 0
        log(f"{len(jobs)} job can xu ly")

        bq = bigquery.Client(project=PROJECT)
        gcs = storage.Client(project=PROJECT)
        bucket = gcs.bucket(BUCKET)
        ov = overrides(conn)
        log(f"{len(ov)} override se duoc ap len so goc")

        failed = 0
        for job in jobs:
            jid = job["id"]
            try:
                with conn.cursor() as cur:
                    cur.execute("UPDATE export_job SET status='running' WHERE id=%s", (jid,))
                conn.commit()
                process(conn, bq, bucket, job, ov)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log(f"  job {jid} LOI: {exc}")
                conn.rollback()
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE export_job SET status='error', finished_at=now(), error=%s
                           WHERE id=%s""", (str(exc)[:500], jid))
                conn.commit()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
