"""Export Job — sinh file deliverable tu ban da ky.

Bon rang buoc quyet dinh noi dung file, theo dung thu tu quan trong:

1. CHI lay nhung lan nap nam trong ban da ky. `signed_version.source_run_ids`
   dong bang danh sach nay luc ky. Khong co no thi file se dinh ca lan nap
   den sau khi ky — du lieu chua ai duyet di thang ra ngoai.
2. CHI lay nhung bang trong pham vi nguoi xin. Pham vi duoc chot luc xin
   file, khong phai luc job chay.
3. So trong file la so cua NGUON, khong sua gi. Ung dung khong con sua so:
   sai thi team Data sua o BigQuery. Nho vay file gui khach va BigQuery
   luon khop nhau — thu ma bang override cu khong bao dam duoc.
4. Excel khong chua qua 1.048.576 dong mot sheet. Vuot thi tach sheet va
   ghi canh bao, khong lang le cat mat du lieu.

Va mot thu di kem file: DAU BAN KY. Hai ban ky cung dinh dang co the co
chat luong khac han nhau — mot ban sach, mot ban ky kem ba luat dang vi
pham va hai ticket chua dong. Sale phai biet minh dang cam ban nao, nen
moi file deu co mot file `.ban-ky.txt` di kem (voi xlsx thi them mot sheet
bia). CSV khong cho nhet dong chu thich vao giua du lieu ma khong lam hong
file, nen dau phai nam rieng.

Doc THANG BigQuery chu khong qua ban sao Postgres: so gui khach phai den
tu nguon su that, khong phu thuoc Sync Job co tre hay khong.
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
HEADER = ["year", "state", "institution_id", "institution", "deposit", "deposit_share"]


def log(m: str) -> None:
    print(f"[export] {m}", flush=True)


# ---------------------------------------------------------------- doc DB

def pending_jobs(conn) -> list[dict]:
    with conn.cursor() as cur:
        base = """SELECT e.id, e.format, e.scope_states, e.requested_by,
                         e.signed_version_id, v.label, v.source_run_ids, v.run_id,
                         v.checksum, v.violations, v.violations_fingerprint,
                         v.rules_version, v.open_tickets, v.approval_note,
                         v.signed_by, v.signed_at
                  FROM export_job e
                  LEFT JOIN signed_version v ON v.id = e.signed_version_id
                  WHERE e.status = 'pending'"""
        if JOB_ID:
            cur.execute(f"{base} AND e.id = %s", (JOB_ID,))
        else:
            cur.execute(f"{base} ORDER BY e.id LIMIT 5")
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def blocking_tickets(conn) -> list[tuple]:
    """Ticket dang chan phat hanh. Vi pham luat KHONG chan nua.

    Vi pham la nghi ngo cua may, va da duoc team lead duyet bang phieu
    duyet luc ky. Ticket chan thi khac han: do la loi duoc xac nhan bang
    bang chung, va no chan cho toi khi nguon that su doi.
    """
    with conn.cursor() as cur:
        cur.execute("""SELECT id, title FROM ticket
                       WHERE status IN ('open','awaiting_verify') AND blocking
                       ORDER BY id""")
        return cur.fetchall()


# --------------------------------------------------------------- doc BQ

def fetch_rows(bq: bigquery.Client, run_ids: list[str], states: list[str] | None):
    """Doc BigQuery theo dung ban ky va dung pham vi.

    ORDER BY dat state, year len truoc co hai tac dung: file doc de, va
    cac dong cung mot nhom thi phan nam lien nhau — nho do tinh lai thi
    phan chi can giu MOT nhom trong bo nho.
    """
    where = ["run_id IN UNNEST(@runs)"]
    params = [bigquery.ArrayQueryParameter("runs", "STRING", run_ids)]
    if states:
        where.append("state IN UNNEST(@states)")
        params.append(bigquery.ArrayQueryParameter("states", "STRING", states))

    sql = f"""
        SELECT year, state, institution_id, institution, deposit, deposit_share
        FROM `{PROJECT}.{DATASET}.{TABLE}`
        WHERE {' AND '.join(where)}
        ORDER BY state, year, deposit DESC
    """
    cfg = bigquery.QueryJobConfig(query_parameters=params)
    return bq.query(sql, location=LOCATION, job_config=cfg).result()


def to_rows(rows):
    """Doi dong BigQuery thanh list theo dung thu tu HEADER.

    Khong con nhom lai theo (year, state) nua: viec gom nhom truoc kia chi
    de tinh lai thi phan sau khi ap override. Khong sua so thi thi phan
    cua nguon van dung, va job chay thang tung dong — it bo nho hon va it
    cho sai hon.
    """
    for r in rows:
        yield [r.year, r.state, r.institution_id, r.institution, r.deposit,
               f"{r.deposit_share:.{SHARE_DIGITS}f}" if r.deposit_share is not None else ""]


# ------------------------------------------------------------ dau ban ky

def stamp_lines(job: dict, states: list[str] | None, n_rows: int) -> list[str]:
    """Noi dung file dau di kem. Doc duoc bang mat thuong, khong phai JSON.

    Nguoi doc no la sale va khach, khong phai may.
    """
    vi_pham = job.get("violations") or {}
    ticket = job.get("open_tickets") or []
    ky_luc = job.get("signed_at")
    lines = [
        "DAU BAN KY — di kem file du lieu",
        "=" * 52,
        f"Ban ky          : {job['label']}  (#{job['signed_version_id']})",
        f"Nguoi ky        : {job.get('signed_by') or '-'}",
        f"Ky luc          : {ky_luc.isoformat() if ky_luc else '-'}",
        f"Lan nap du lieu : {', '.join(job['source_run_ids'])}",
        f"Van tay du lieu : {job.get('checksum') or '(khong ghi)'}",
        f"Bo luat QC      : version {job.get('rules_version') or '-'}",
        f"Pham vi file    : {', '.join(states) if states else 'tat ca cac bang'}",
        f"So dong         : {n_rows:,}",
        "",
    ]
    if vi_pham:
        lines.append("Luc ky VAN CON vi pham luat — da duoc duyet cho qua:")
        for rule, n in sorted(vi_pham.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - {rule}: {n:,} o")
        lines.append(f"  van tay tap vi pham: {job.get('violations_fingerprint') or '-'}")
    else:
        lines.append("Luc ky khong con vi pham luat nao.")
    lines.append("")
    if ticket:
        lines.append("Ticket CHUA DONG luc ky (loi da xac nhan, dang cho nguon sua):")
        lines.append("  " + ", ".join(f"#{t}" for t in ticket))
    else:
        lines.append("Khong con ticket nao chua dong luc ky.")
    lines.append("")
    if job.get("approval_note"):
        lines.append("Phieu duyet cua nguoi ky:")
        for dong in str(job["approval_note"]).splitlines():
            lines.append(f"  {dong}")
    lines.append("")
    lines.append("So trong file la so cua BigQuery tai cac lan nap ke tren.")
    lines.append("Ung dung khong sua so, nen file nay va nguon luon khop nhau.")
    return lines


# ------------------------------------------------------------- ghi file

def write_csv(path: str, rows, stamp: list[str] | None = None) -> tuple[int, str | None]:
    """CSV thuan: chi tieu de va du lieu.

    Dau ban ky KHONG duoc nhet vao day. Mot dong chu thich o dau file lam
    Excel doc lech cot va lam moi parser phia khach hong — dau di ra file
    rieng, thu ma `stamp` o day chi nhan de giu chung mot chu ky ham voi
    write_xlsx.
    """
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for row in rows:
            w.writerow(row)
            n += 1
    return n, None


def write_xlsx(path: str, rows, stamp: list[str] | None = None) -> tuple[int, str | None]:
    """Ghi xlsx o che do write_only — khong dung ca bang trong bo nho.

    Vuot gioi han mot sheet thi mo sheet tiep chu khong cat bot dong, va
    tra ve canh bao de giao dien noi ro voi nguoi tai file.

    Sheet dau tien la BIA ghi dau ban ky. Dat truoc du lieu vi Excel mo
    dung sheet dau: nguoi mo file thay minh dang cam ban nao truoc khi
    thay so.
    """
    from openpyxl import Workbook

    wb = Workbook(write_only=True)
    if stamp:
        bia = wb.create_sheet("Ban ky")
        for dong in stamp:
            bia.append([dong])
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

def process(conn, bq, bucket, job: dict) -> None:
    jid = job["id"]
    if not job["signed_version_id"] or not job["source_run_ids"]:
        raise RuntimeError("job khong gan voi ban ky nao co danh sach lan nap")

    # Cong co the vua khoa lai sau luc xin file — ai do mo mot ticket chan.
    # File da sinh ra roi thi kho thu hoi, nen kiem lai ngay truoc khi ghi.
    chan = blocking_tickets(conn)
    if chan:
        ds = ", ".join(f"#{t[0]}" for t in chan)
        raise RuntimeError(f"cong phat hanh dang khoa ({len(chan)} ticket chan: {ds})")

    fmt = job["format"]
    states = job["scope_states"]
    log(f"  job {jid}: ban ky '{job['label']}' · {len(job['source_run_ids'])} lan nap "
        f"· pham vi {states or 'tat ca'} · {fmt}")

    rows = to_rows(fetch_rows(bq, job["source_run_ids"], states))
    suffix = ".xlsx" if fmt == "xlsx" else ".csv"

    # Dau duoc dung TRUOC khi ghi, nhung so dong thi chi biet sau khi ghi
    # xong — nen dung mot ban tam de nhet vao sheet bia, roi ghi file dau
    # rieng voi con so that.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        local = tmp.name
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        local_stamp = tmp.name
    try:
        writer = write_xlsx if fmt == "xlsx" else write_csv
        n, warning = writer(local, rows, stamp_lines(job, states, 0))

        base = f"exports/{job['run_id']}/deliverable-{jid}"
        path = f"{base}{suffix}"
        bucket.blob(path).upload_from_filename(local)

        with open(local_stamp, "w", encoding="utf-8") as f:
            f.write("\n".join(stamp_lines(job, states, n)) + "\n")
        stamp_path = f"{base}.ban-ky.txt"
        bucket.blob(stamp_path).upload_from_filename(local_stamp)
    finally:
        os.remove(local)
        os.remove(local_stamp)

    log(f"  job {jid}: {n:,} dong -> gs://{BUCKET}/{path}")
    log(f"  job {jid}: dau ban ky -> gs://{BUCKET}/{stamp_path}")
    if warning:
        log(f"  job {jid}: CANH BAO {warning}")

    with conn.cursor() as cur:
        cur.execute(
            """UPDATE export_job SET status='done', finished_at=now(), gcs_path=%s,
                      stamp_path=%s, row_count=%s, warning=%s
               WHERE id=%s""",
            (f"gs://{BUCKET}/{path}", f"gs://{BUCKET}/{stamp_path}", n, warning, jid))
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

        failed = 0
        for job in jobs:
            jid = job["id"]
            try:
                with conn.cursor() as cur:
                    cur.execute("UPDATE export_job SET status='running' WHERE id=%s", (jid,))
                conn.commit()
                process(conn, bq, bucket, job)
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
