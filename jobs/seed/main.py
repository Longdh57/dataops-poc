"""Seed du lieu demo: nguoi dung thu nghiem, va bang fact tren BigQuery.

Pham vi trong plan la "quoc gia"; dataset nay la USA Names nen pham vi
la BANG. Y nghia khong doi: analyst chi thay duoc phan du lieu duoc gan.

Bang fact chi duoc tao khi dat SEED_BIGQUERY=1. Trong dung tinh than
"ung dung khong ghi vao BigQuery": day la buoc dung MOI TRUONG DEMO cho
mot project trong, khong phai viec ung dung lam khi chay. O du an that,
buoc nay thuoc ve Data Engineer.
"""

import os
import sys

import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dataops:dataops@localhost:5432/dataops")
OWNER = os.getenv("OWNER_EMAIL", "longbloginfo@gmail.com")

SEED_BIGQUERY = os.getenv("SEED_BIGQUERY") == "1"
PROJECT = os.getenv("GCP_PROJECT_ID", "dataops-poc-2026")
DATASET = os.getenv("BQ_DATASET", "dataops_src")
TABLE = os.getenv("BQ_TABLE", "fact_names")
LOCATION = os.getenv("BQ_LOCATION", "asia-southeast1")
# Chi lay tu nam nay tro di cho du lieu demo gon nhe.
FROM_YEAR = int(os.getenv("SEED_FROM_YEAR", "2009"))

USERS = [
    (OWNER,                      "Chu he thong",      "admin",     None),
    ("lead@dataops.test",        "Team Lead",         "team_lead", None),
    ("analyst.tx@dataops.test",  "Analyst Texas",     "analyst",   ["TX"]),
    ("analyst.ca@dataops.test",  "Analyst California","analyst",   ["CA"]),
    ("sale@dataops.test",        "Sale",              "sale",      ["CA", "TX"]),
]


# Dung y nghia cua tung cot duoc tinh o day, khong phai o cho khac:
#   market_share = ty trong cua mot ten trong tong so tre cung
#                  (nam, bang, gioi tinh) — cong lai dung bang 1.0
#   prev_number  = so cua chinh ten do, lan gan nhat truoc do co du lieu
#   prev_year    = nam cua lan do. Cach nhau >3 nam la mot ngoai le.
SEED_SQL = """
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.{table}`
PARTITION BY DATE(loaded_at)
CLUSTER BY state, gender, year
AS
WITH src AS (
  SELECT year, state, gender, name, number
  FROM `bigquery-public-data.usa_names.usa_1910_current`
  WHERE year >= {from_year}
),
voi_nam_truoc AS (
  SELECT *,
         LAG(number) OVER w AS prev_number,
         LAG(year)   OVER w AS prev_year
  FROM src
  WINDOW w AS (PARTITION BY state, gender, name ORDER BY year)
)
SELECT
  '{run_id}' AS run_id,
  CURRENT_TIMESTAMP() AS loaded_at,
  year, state, gender, name, number,
  SAFE_DIVIDE(number, SUM(number) OVER (PARTITION BY year, state, gender)) AS market_share,
  prev_number, prev_year
FROM voi_nam_truoc
"""


def seed_bigquery() -> None:
    """Tao bang fact demo tu du lieu that cua Cuc An sinh Xa hoi My.

    CREATE TABLE IF NOT EXISTS: chay lai lan hai khong lam gi ca, khong
    de doi mat du lieu dang co.
    """
    from datetime import datetime, timezone

    from google.cloud import bigquery

    bq = bigquery.Client(project=PROJECT)
    bq.create_dataset(bigquery.Dataset(f"{PROJECT}.{DATASET}"), exists_ok=True)

    run_id = f"run-{datetime.now(timezone.utc):%Y-%m-%d}-001"
    sql = SEED_SQL.format(project=PROJECT, dataset=DATASET, table=TABLE,
                          from_year=FROM_YEAR, run_id=run_id)
    job = bq.query(sql, location=LOCATION)
    job.result()
    print(f"[seed] bang {PROJECT}.{DATASET}.{TABLE} san sang · run_id={run_id} "
          f"· quet {(job.total_bytes_processed or 0) / 1e6:.0f} MB", flush=True)


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
