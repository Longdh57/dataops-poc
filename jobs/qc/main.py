"""QC Runner — hai viec, chay sau moi lan nap.

1. Ap bo luat trong rules/rules.yaml len fact_current. Luat nam trong file
   cau hinh chu khong trong code: them luat moi chi can them mot muc vao
   YAML roi chay lai job nay.

2. Doi chieu tung ticket dang song voi so THAT trong lan nap vua ve. Day
   la cho duy nhat ticket duoc dong. Nguoi khong dong duoc ticket — ke ca
   nguoi da sua — vi "da sua xong roi" la loi hua, con cot nay la bang
   chung.

Vi pham KHONG co trang thai va thuoc ve dung mot lan nap: moi lan chay,
toan bo vi pham cua lan nap do bi thay the. Ai cho qua cai gi thi nam o
`signed_version.approval_note`, khong nam o day.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import yaml
from google.cloud import bigquery
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dataops:dataops@localhost:5432/dataops")
RULES_PATH = Path(os.getenv("RULES_PATH", "/srv/rules/rules.yaml"))

# Day anh chup qc_exception len BigQuery cho bao cao/BI phia khach hang.
# Ung dung VAN doc tu Postgres (khong doi duong doc, tiet kiem chi phi
# query BigQuery) — day chi la mot ban sao chieu di mot huong.
MIRROR_QC_TO_BIGQUERY = os.getenv("MIRROR_QC_TO_BIGQUERY") == "1"
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
BQ_ANALYTICS_DATASET = os.getenv("BQ_ANALYTICS_DATASET", "dataops_analytics")
BQ_ANALYTICS_TABLE = os.getenv("BQ_ANALYTICS_TABLE", "qc_exception")
BQ_LOCATION = os.getenv("BQ_LOCATION", "asia-southeast1")

QC_EXCEPTION_BQ_SCHEMA = [
    bigquery.SchemaField("id", "INTEGER"),
    bigquery.SchemaField("run_id", "STRING"),
    bigquery.SchemaField("rule_id", "STRING"),
    bigquery.SchemaField("severity", "STRING"),
    bigquery.SchemaField("year", "INTEGER"),
    bigquery.SchemaField("state", "STRING"),
    bigquery.SchemaField("institution_id", "INTEGER"),
    bigquery.SchemaField("institution", "STRING"),
    bigquery.SchemaField("message", "STRING"),
    bigquery.SchemaField("observed", "JSON"),
    bigquery.SchemaField("created_at", "TIMESTAMP"),
    bigquery.SchemaField("synced_at", "TIMESTAMP"),
]


SEVERITIES = {"critical", "warning", "info"}


def log(msg: str) -> None:
    print(f"[qc] {msg}", flush=True)


# ------------------------------------------------------------- ticket

def verify_tickets(conn: psycopg.Connection, run_id: str) -> dict[str, int]:
    """Doi chieu ticket voi so that, roi dong / bat lai / de nguyen.

    Ba ket qua, khong co ket qua thu tu:

    - so that KHOP `expected_value` -> dong, ghi lai dong o lan nap nao.
    - lech, ma nguoi ta da bao "da sua" -> bat nguoc ve `open` kem so doc
      duoc. Im lang o day la cach de mot ban sai di ra ngoai.
    - lech, va chua ai bao da sua -> de nguyen, chi ghi lai lan kiem.

    Dong bien mat khoi nguon cung tinh la chua xac minh duoc: khong doc
    duoc so thi khong ket luan duoc gi.
    """
    with conn.cursor() as cur:
        cur.execute("""SELECT t.id, t.status, t.expected_value, t.blocking,
                              t.state, t.institution_id, t.year, t.institution, f.deposit
                       FROM ticket t
                       LEFT JOIN fact_current f
                         ON f.year = t.year AND f.state = t.state
                        AND f.institution_id = t.institution_id
                       WHERE t.status IN ('open', 'awaiting_verify')
                       ORDER BY t.id""")
        rows = cur.fetchall()

    dem = {"dong": 0, "bat_lai": 0, "con_mo": 0}
    with conn.cursor() as cur:
        for tid, status, expected, blocking, state, institution_id, year, institution, deposit in rows:
            quan_sat = None if deposit is None else str(deposit)
            khoa = f"{state}/{institution}/{year}"

            if quan_sat is not None and quan_sat == expected:
                cur.execute(
                    """UPDATE ticket SET status='closed', closed_run_id=%s, closed_at=now(),
                              last_checked_run_id=%s, last_checked_at=now(), last_observed=%s
                       WHERE id=%s""", (run_id, run_id, quan_sat, tid))
                dem["dong"] += 1
                log(f"  ticket #{tid} {khoa}: nguon da la {expected} -> DONG")
            elif status == "awaiting_verify":
                cur.execute(
                    """UPDATE ticket SET status='open', last_checked_run_id=%s,
                              last_checked_at=now(), last_observed=%s
                       WHERE id=%s""", (run_id, quan_sat, tid))
                dem["bat_lai"] += 1
                log(f"  ticket #{tid} {khoa}: bao da sua nhung doc duoc "
                    f"{quan_sat or '(khong con dong)'}, can {expected} -> BAT LAI")
            else:
                cur.execute(
                    """UPDATE ticket SET last_checked_run_id=%s, last_checked_at=now(),
                              last_observed=%s WHERE id=%s""", (run_id, quan_sat, tid))
                dem["con_mo"] += 1
    conn.commit()
    return dem


def validate(rules: list[dict]) -> list[str]:
    """Bat loi cau hinh TRUOC khi chay, va bat het mot luot.

    File luat la thu duoc sua thuong xuyen nhat trong ca he thong, boi
    nguoi khong doc code. Mot luat thieu severity ma chi bao loi luc chay
    SQL thi nguoi sua phai doan; bao ro tu day thi khong.
    """
    loi: list[str] = []
    seen: set[str] = set()
    for i, r in enumerate(rules):
        ten = r.get("id") or f"luat thu {i + 1}"
        if not r.get("id"):
            loi.append(f"{ten}: thieu 'id'")
        elif r["id"] in seen:
            loi.append(f"{ten}: trung 'id' voi luat khac")
        else:
            seen.add(r["id"])
        if r.get("severity") not in SEVERITIES:
            loi.append(f"{ten}: 'severity' phai la mot trong {sorted(SEVERITIES)}, "
                       f"dang la {r.get('severity')!r}")
        if not r.get("message"):
            loi.append(f"{ten}: thieu 'message' — day la cau nguoi dung doc")
        if not r.get("sql"):
            loi.append(f"{ten}: thieu 'sql'")
        scope = r.get("scope")
        if scope is not None and (not isinstance(scope, list) or not scope):
            loi.append(f"{ten}: 'scope' phai la danh sach bang, hoac bo han di")
    return loi


def scope_filter(rule: dict) -> tuple[str, list]:
    """Pham vi cua luat: chi ap cho mot so bang.

    Co luat chi dung o vai thi truong — nguong kiem duyet cua moi noi mot
    khac. Khai bao bang cau hinh thay vi nhet dieu kien vao SQL de nguoi
    doc thay ngay luat nay cham vao dau.
    """
    scope = rule.get("scope")
    if not scope:
        return "", []
    return "WHERE x.state = ANY(%s)", [[s.upper() for s in scope]]


# --------------------------------------------------- day len BigQuery

def qc_exception_rows_for_bigquery(rows: list[dict], synced_at: str) -> list[dict]:
    """Chuyen dong doc tu Postgres sang dang nap duoc vao BigQuery.

    Tach rieng khoi phan goi API that de test duoc ma khong can BigQuery:
    datetime phai thanh chuoi ISO, con `observed` (jsonb) giu nguyen vi
    BigQuery nhan thang object cho cot kieu JSON.
    """
    return [
        {
            "id": r["id"],
            "run_id": r["run_id"],
            "rule_id": r["rule_id"],
            "severity": r["severity"],
            "year": r["year"],
            "state": r["state"],
            "institution_id": r["institution_id"],
            "institution": r["institution"],
            "message": r["message"],
            "observed": r["observed"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "synced_at": synced_at,
        }
        for r in rows
    ]


def mirror_qc_exception_to_bigquery(conn: psycopg.Connection) -> None:
    """Day TOAN BO bang qc_exception len BigQuery — anh chup THAY THE.

    Khong tu tich luy lich su rieng ben BigQuery vi khong can: Postgres
    khong bao gio xoa vi pham cua run_id cu (DELETE trong main() chi dong
    voi dung run_id vua quet), nen ban sao nay da mang theo du lich su co
    trong Postgres. WRITE_TRUNCATE moi lan chi dam bao BigQuery khop dung
    Postgres tai thoi diem day, khong con o rac cua lan day truoc.

    Buoc nay chi phuc vu bao cao/BI phia khach hang tren BigQuery — ung
    dung van doc/ghi qua Postgres nhu truoc, khong doi duong doc.
    """
    if not MIRROR_QC_TO_BIGQUERY:
        return
    if not GCP_PROJECT_ID:
        log("MIRROR_QC_TO_BIGQUERY=1 nhung thieu GCP_PROJECT_ID — bo qua day len BigQuery")
        return

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT id, run_id, rule_id, severity, year, state, institution_id, institution,
                              message, observed, created_at
                       FROM qc_exception ORDER BY id""")
        rows = cur.fetchall()

    synced_at = datetime.now(timezone.utc).isoformat()
    payload = qc_exception_rows_for_bigquery(rows, synced_at)
    table_id = f"{GCP_PROJECT_ID}.{BQ_ANALYTICS_DATASET}.{BQ_ANALYTICS_TABLE}"

    # Khong lam hong ca lan chay QC vi mot buoc phu: du lieu that (Postgres)
    # da ghi xong truoc do. Day hong thi log ro, lan chay sau day lai ban
    # moi nhat — khong can retry rieng.
    try:
        bq = bigquery.Client(project=GCP_PROJECT_ID)
        job_config = bigquery.LoadJobConfig(
            schema=QC_EXCEPTION_BQ_SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        )
        job = bq.load_table_from_json(
            payload, table_id, job_config=job_config, location=BQ_LOCATION)
        job.result()
        log(f"day {len(payload):,} dong len BigQuery {table_id} (anh chup thay the)")
    except Exception as exc:  # noqa: BLE001
        log(f"khong day len BigQuery duoc ({table_id}): {exc}")


def main() -> int:
    if not RULES_PATH.exists():
        log(f"khong thay file luat: {RULES_PATH}")
        return 1

    config = yaml.safe_load(RULES_PATH.read_text())
    rules = config["rules"]
    # Ghi lai de ban ky cheo duoc: "team lead duyet duoi bo luat version
    # may". Thieu no thi mot quyet dinh cu khong tai hien duoc, vi file
    # luat la thu bi sua thuong xuyen nhat trong ca he thong.
    rules_version = config.get("version")

    if loi := validate(rules):
        log(f"file luat co {len(loi)} loi — KHONG chay luat nao:")
        for m in loi:
            log(f"  - {m}")
        return 1
    log(f"nap {len(rules)} luat (version {rules_version}) tu {RULES_PATH}")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT last_run_id, qc_run_id FROM sync_state WHERE id = 1")
            row = cur.fetchone()
            if not row or not row[0]:
                log("chua co lan dong bo nao — khong co gi de kiem")
                return 0
            run_id, da_kiem = row
        # Bo qua neu run nay da duoc kiem roi — cung tinh than voi Sync Job:
        # khong lam viec thua. Dat FORCE_QC=1 de ep chay lai.
        if os.getenv("FORCE_QC") != "1" and da_kiem == run_id:
            log(f"run {run_id} da duoc kiem — bo qua")
            return 0

        log(f"kiem tren run {run_id}")

        totals: dict[str, int] = {}
        with conn.cursor() as cur:
            # Thay the TOAN BO vi pham cua lan nap nay. Vi pham khong co
            # trang thai nen khong co gi de giu lai: danh sach phai la anh
            # chup cua du lieu dang co, khong phai cua lan chay truoc.
            cur.execute("DELETE FROM qc_exception WHERE run_id = %s", (run_id,))
            if cur.rowcount:
                log(f"thay the {cur.rowcount:,} vi pham cu cua chinh lan nap nay")

            for rule in rules:
                where, scope_params = scope_filter(rule)
                cur.execute(
                    f"""
                    INSERT INTO qc_exception
                        (run_id, rule_id, severity, year, state, institution_id, institution, message, observed)
                    SELECT %s, %s, %s, x.year, x.state, x.institution_id, x.institution, %s, x.observed
                    FROM ({rule['sql']}) x
                    {where}
                    """,
                    (run_id, rule["id"], rule["severity"], rule["message"], *scope_params),
                )
                totals[rule["id"]] = cur.rowcount
                pham_vi = f" [{','.join(rule['scope'])}]" if rule.get("scope") else ""
                log(f"  {rule['id']:26} {rule['severity']:9} {cur.rowcount:>6,}{pham_vi}")
        conn.commit()

        # Ticket sau luat: ca hai deu doc fact_current cua cung lan nap,
        # nen ket qua nhat quan voi nhau.
        log("doi chieu ticket voi so that:")
        tk = verify_tickets(conn, run_id)
        log(f"  dong {tk['dong']} · bat lai {tk['bat_lai']} · con mo {tk['con_mo']}")

        with conn.cursor() as cur:
            cur.execute("""UPDATE sync_state
                           SET qc_run_id=%s, qc_checked_at=now(), rules_version=%s
                           WHERE id=1""", (run_id, rules_version))
        conn.commit()

        mirror_qc_exception_to_bigquery(conn)

        with conn.cursor() as cur:
            cur.execute("""SELECT severity, count(*) FROM qc_exception
                           WHERE run_id = %s GROUP BY severity ORDER BY severity""", (run_id,))
            summary = dict(cur.fetchall())
            cur.execute("""SELECT count(*) FROM ticket
                           WHERE status IN ('open','awaiting_verify') AND blocking""")
            chan = cur.fetchone()[0]

    log(f"vi pham lan nap nay: {summary}")
    # Vi pham luat KHONG khoa cong nua — chung la nghi ngo cua may, va
    # team lead duyet bang phieu duyet co ten. Chi ticket chan moi khoa.
    log(f"cong phat hanh: {'KHOA' if chan else 'SAN SANG'} ({chan} ticket dang chan)")
    if summary:
        log("  — con vi pham luat: ky duoc, nhung phai co phieu duyet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
