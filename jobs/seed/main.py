"""Seed du lieu demo: nguoi dung thu nghiem, va bang fact tren BigQuery.

Pham vi trong plan la "quoc gia"; dataset nay la FDIC Summary of Deposits
nen pham vi la BANG. Y nghia khong doi: analyst chi thay duoc phan du lieu
duoc gan.

Bang fact chi duoc tao khi dat SEED_BIGQUERY=1. Trong dung tinh than
"ung dung khong ghi vao BigQuery": day la buoc dung MOI TRUONG DEMO cho
mot project trong, khong phai viec ung dung lam khi chay. O du an that,
buoc nay thuoc ve Data Engineer.

Khac voi nguon cong khai khac: FDIC Summary of Deposits KHONG co san tren
bigquery-public-data (chi co snapshot to chuc/chi nhanh, khong co lich su
theo nam), nen khong the viet mot cau CREATE TABLE ... AS SELECT don gian
nhu truoc. Buoc nay tu goi API cong khai cua FDIC (khong can key), nap
(LOAD) du lieu tho vao mot bang tam tren BigQuery, roi moi chay mot cau SQL
gop + tinh deposit_share/prev_deposit tren bang tam do.
"""

import io
import json
import os
import sys
import time
import urllib.request

import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dataops:dataops@localhost:5432/dataops")
OWNER = os.getenv("OWNER_EMAIL", "longbloginfo@gmail.com")

SEED_BIGQUERY = os.getenv("SEED_BIGQUERY") == "1"
# Du lieu FDIC that gan nhu khong bao gio tu vi pham 2 luat "toan ven cong
# thuc" (deposit_share duoc tinh dung tu dau) hay luat "tai xuat sau khoang
# trong" (5 nam seed qua ngan de co gap that > 3 nam). Bat co nay de pha vai
# dong that thanh du lieu gia, dam bao demo QC luon co du vi du cho ca 6
# luat trong rules.yaml — khong dung cho pipeline that.
SEED_FAKE_VIOLATIONS = os.getenv("SEED_FAKE_VIOLATIONS") == "1"
PROJECT = os.getenv("GCP_PROJECT_ID", "dataops-poc-2026")
DATASET = os.getenv("BQ_DATASET", "dataops_src")
TABLE = os.getenv("BQ_TABLE", "fact_names")
STAGE_TABLE = os.getenv("BQ_STAGE_TABLE", "sod_raw_stage")
LOCATION = os.getenv("BQ_LOCATION", "asia-southeast1")
# So nam gan nhat lay tu FDIC, tinh nguoc tu nam moi nhat API co — khong
# hard-code nam cu the nen khong bi "het han" theo thoi gian.
SEED_YEAR_COUNT = int(os.getenv("SEED_YEAR_COUNT", "5"))

FDIC_API = "https://api.fdic.gov/banks/sod"
FDIC_FIELDS = "YEAR,STALPBR,CERT,NAMEFULL,DEPSUMBR"
FDIC_PAGE_LIMIT = 10000

# Chon 3 dong dau tien (theo institution_id) cua 3 nhom (year, state) khac
# nhau co tu 2 to chuc tro len, roi cong lech deposit_share cua dung dong
# do +0.05 — dong bi sua vua sai cong thuc rieng no (deposit_share_formula_
# mismatch), vua keo tong ca nhom lech khoi 1.0 (deposit_share_sum_not_100),
# nen 3 dong nay phu du 2 luat cung luc.
FAKE_SHARE_MISMATCH_SQL = """
UPDATE `{project}.{dataset}.{table}` t
SET deposit_share = t.deposit_share + 0.05
FROM (
  SELECT year, state, institution_id
  FROM (
    SELECT year, state, institution_id,
           ROW_NUMBER() OVER (PARTITION BY year, state ORDER BY institution_id) AS rn,
           COUNT(*) OVER (PARTITION BY year, state) AS grp_size
    FROM `{project}.{dataset}.{table}`
  )
  WHERE rn = 1 AND grp_size > 1
  ORDER BY year, state
  LIMIT 3
) bad
WHERE t.year = bad.year AND t.state = bad.state AND t.institution_id = bad.institution_id
"""

# Chon dong co nam moi nhat (deterministic, co prev_year that), ghi de
# prev_year/prev_deposit — hai cot nay la du lieu da tinh san (LAG) ma luat
# doc thang, nen sua truc tiep la du de gia lap "bien mat > 3 nam roi tai
# xuat voi deposit >= 100M" ma khong can dung that mot chuoi nam dai hon
# SEED_YEAR_COUNT.
FAKE_GAP_REAPPEAR_SQL = """
UPDATE `{project}.{dataset}.{table}` t
SET prev_year = t.year - 4, prev_deposit = 150000
FROM (
  SELECT year, state, institution_id
  FROM `{project}.{dataset}.{table}`
  WHERE prev_year IS NOT NULL
  ORDER BY year DESC, state, institution_id
  LIMIT 1
) bad
WHERE t.year = bad.year AND t.state = bad.state AND t.institution_id = bad.institution_id
"""

USERS = [
    (OWNER,                      "Chu he thong",      "admin",     None),
    ("lead@dataops.test",        "Team Lead",         "team_lead", None),
    ("analyst.tx@dataops.test",  "Analyst Texas",     "analyst",   ["TX"]),
    ("analyst.ca@dataops.test",  "Analyst California","analyst",   ["CA"]),
    ("sale@dataops.test",        "Sale",              "sale",      ["CA", "TX"]),
]


# Dung y nghia cua tung cot duoc tinh o day, khong phai o cho khac:
#   deposit_share = ty trong deposit cua mot to chuc trong tong deposit
#                   cua ca bang, nam do — cong lai dung bang 1.0
#   prev_deposit  = deposit cua chinh to chuc do, nam gan nhat truoc do co
#                   du lieu. prev_year = nam cua lan do.
# GROUP BY o day gop tu muc chi nhanh (moi to chuc nhieu chi nhanh trong
# cung mot bang) len muc to chuc — dung dung grain (year, state,
# institution_id) ma phan con lai cua he thong mong doi.
AGG_SQL = """
CREATE OR REPLACE TABLE `{project}.{dataset}.{table}`
PARTITION BY DATE(loaded_at)
CLUSTER BY state, institution_id, year
AS
WITH src AS (
  SELECT YEAR AS year, STALPBR AS state, CERT AS institution_id,
         ANY_VALUE(NAMEFULL) AS institution, SUM(DEPSUMBR) AS deposit
  FROM `{project}.{dataset}.{stage_table}`
  GROUP BY YEAR, STALPBR, CERT
),
voi_nam_truoc AS (
  SELECT *,
         LAG(deposit) OVER w AS prev_deposit,
         LAG(year)    OVER w AS prev_year
  FROM src
  WINDOW w AS (PARTITION BY state, institution_id ORDER BY year)
)
SELECT
  '{run_id}' AS run_id,
  CURRENT_TIMESTAMP() AS loaded_at,
  year, state, institution_id, institution, deposit,
  SAFE_DIVIDE(deposit, SUM(deposit) OVER (PARTITION BY year, state)) AS deposit_share,
  prev_deposit, prev_year
FROM voi_nam_truoc
"""


def latest_fdic_year() -> int:
    """Nam moi nhat FDIC da cong bo — dung lam moc tinh nguoc SEED_YEAR_COUNT nam."""
    url = f"{FDIC_API}?limit=1&sort_by=YEAR&sort_order=DESC&format=json"
    with urllib.request.urlopen(url, timeout=30) as resp:
        body = json.load(resp)
    return int(body["data"][0]["data"]["YEAR"])


def fetch_fdic_year(year: int) -> list[dict]:
    """Tai toan bo du lieu chi nhanh cua mot nam, phan trang bang offset."""
    rows: list[dict] = []
    offset = 0
    while True:
        url = (f"{FDIC_API}?filters=YEAR:{year}&fields={FDIC_FIELDS}"
               f"&limit={FDIC_PAGE_LIMIT}&offset={offset}&format=json")
        with urllib.request.urlopen(url, timeout=60) as resp:
            body = json.load(resp)
        batch = body.get("data", [])
        if not batch:
            break
        rows.extend(r["data"] for r in batch)
        if len(batch) < FDIC_PAGE_LIMIT:
            break
        offset += FDIC_PAGE_LIMIT
        time.sleep(0.2)  # lich su voi API cong khai, khong key
    return rows


def seed_bigquery() -> None:
    """Tao bang fact demo tu du lieu that cua FDIC Summary of Deposits.

    CREATE OR REPLACE: chay lai lan hai se nap lai tu dau — khac
    CREATE TABLE IF NOT EXISTS cua nguon cu, vi o day khong co bang cong
    khai co san de dua vao lam "da co roi thi thoi"; du lieu tu API co the
    thay doi (FDIC cap nhat), nen seed lai la hop ly.
    """
    from datetime import datetime, timezone

    from google.cloud import bigquery

    to_year = latest_fdic_year()
    years = list(range(to_year - SEED_YEAR_COUNT + 1, to_year + 1))

    bq = bigquery.Client(project=PROJECT)
    bq.create_dataset(bigquery.Dataset(f"{PROJECT}.{DATASET}"), exists_ok=True)

    rows: list[dict] = []
    for year in years:
        year_rows = fetch_fdic_year(year)
        rows.extend(year_rows)
        print(f"[seed] FDIC {year}: {len(year_rows):,} dong chi nhanh", flush=True)

    stage_id = f"{PROJECT}.{DATASET}.{STAGE_TABLE}"
    ndjson = "\n".join(json.dumps(r) for r in rows).encode()
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    job = bq.load_table_from_file(io.BytesIO(ndjson), stage_id,
                                  job_config=job_config, location=LOCATION)
    job.result()
    print(f"[seed] nap {len(rows):,} dong chi nhanh vao bang tam {stage_id}", flush=True)

    # DROP truoc thay vi CREATE OR REPLACE: BigQuery tu choi REPLACE khi
    # cluster/partition spec doi (o day co that, cluster tu doi
    # "state, gender, year" sang "state, institution_id, year" khi day la
    # lan dau chay seed FDIC tren mot bang fact_names cu con lai).
    bq.delete_table(f"{PROJECT}.{DATASET}.{TABLE}", not_found_ok=True)

    run_id = f"run-{datetime.now(timezone.utc):%Y-%m-%d}-001"
    sql = AGG_SQL.format(project=PROJECT, dataset=DATASET, table=TABLE,
                        stage_table=STAGE_TABLE, run_id=run_id)
    job = bq.query(sql, location=LOCATION)
    job.result()
    print(f"[seed] bang {PROJECT}.{DATASET}.{TABLE} san sang · run_id={run_id} "
          f"· nam {years[0]}-{years[-1]} · quet {(job.total_bytes_processed or 0) / 1e6:.0f} MB", flush=True)

    if SEED_FAKE_VIOLATIONS:
        _inject_demo_violations(bq)


def _inject_demo_violations(bq) -> None:
    """Pha vai dong that thanh du lieu gia de dam bao QC co it nhat 1 vi
    pham cho 3 luat ma du lieu FDIC that gan nhu khong bao gio tu vi pham:
    deposit_share_sum_not_100, deposit_share_formula_mismatch (cong thuc
    duoc tinh dung tu dau) va institution_reappeared_after_gap (5 nam seed
    qua ngan de co khoang trong that > 3 nam). 3 luat con lai
    (deposit_negative_or_zero, deposit_spike, unusual_deposit_change) da
    tu nhien co hang tram vi pham tren du lieu that nen khong can gia.
    """
    for label, sql in [
        ("deposit_share_formula_mismatch + deposit_share_sum_not_100", FAKE_SHARE_MISMATCH_SQL),
        ("institution_reappeared_after_gap", FAKE_GAP_REAPPEAR_SQL),
    ]:
        job = bq.query(sql.format(project=PROJECT, dataset=DATASET, table=TABLE), location=LOCATION)
        job.result()
        print(f"[seed] fake violation cho {label}: {job.num_dml_affected_rows} dong", flush=True)


def main() -> int:
    if SEED_BIGQUERY:
        seed_bigquery()

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for email, name, role, scope in USERS:
                cur.execute(
                    """INSERT INTO app_user (email, display_name, is_active)
                       VALUES (%s, %s, true)
                       ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
                       RETURNING id""",
                    (email, name))
                uid = cur.fetchone()[0]
                cur.execute(
                    """INSERT INTO app_role (user_id, role, scope_states)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (user_id, role) DO UPDATE SET scope_states = EXCLUDED.scope_states""",
                    (uid, role, psycopg.types.json.Json(scope) if scope else None))
                print(f"[seed] {email:28} {role:10} pham vi: {scope or 'tat ca'}", flush=True)
        conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
