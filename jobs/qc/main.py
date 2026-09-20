"""QC Runner — ap bo luat trong rules/rules.yaml len fact_current.

Luat nam trong file cau hinh, khong nam trong code: them luat moi chi can
them mot muc vao YAML roi chay lai job nay.

Idempotent: ngoai le dang `open` cua run hien tai bi xoa va sinh lai; ngoai
le da duoc xu ly (applied/parked/sent_back) KHONG bao gio bi dong toi.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import yaml

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dataops:dataops@localhost:5432/dataops")
RULES_PATH = Path(os.getenv("RULES_PATH", "/srv/rules/rules.yaml"))


def log(msg: str) -> None:
    print(f"[qc] {msg}", flush=True)


def main() -> int:
    if not RULES_PATH.exists():
        log(f"khong thay file luat: {RULES_PATH}")
        return 1

    config = yaml.safe_load(RULES_PATH.read_text())
    rules = config["rules"]
    log(f"nap {len(rules)} luat tu {RULES_PATH}")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT last_run_id FROM sync_state WHERE id = 1")
            row = cur.fetchone()
            if not row or not row[0]:
                log("chua co lan dong bo nao — khong co gi de kiem")
                return 0
            run_id = row[0]
        # Bo qua neu run nay da duoc kiem roi — cung tinh than voi Sync Job:
        # khong lam viec thua. Dat FORCE_QC=1 de ep chay lai.
        if os.getenv("FORCE_QC") != "1":
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM qc_exception WHERE run_id = %s", (run_id,))
                if cur.fetchone()[0] > 0:
                    log(f"run {run_id} da duoc kiem — bo qua")
                    return 0

        log(f"kiem tren run {run_id}")

        totals: dict[str, int] = {}
        with conn.cursor() as cur:
            # Chi xoa ngoai le CHUA duoc xu ly. Nguoi dung da quyet dinh
            # thi quyet dinh do phai con nguyen.
            cur.execute("DELETE FROM qc_exception WHERE run_id = %s AND status = 'open'", (run_id,))
            log(f"xoa {cur.rowcount:,} ngoai le open cu")

            for rule in rules:
                cur.execute(
                    f"""
                    INSERT INTO qc_exception
                        (run_id, rule_id, severity, year, state, gender, name, message, observed, status)
                    SELECT %s, %s, %s, x.year, x.state, x.gender, x.name, %s, x.observed, 'open'
                    FROM ({rule['sql']}) x
                    """,
                    (run_id, rule["id"], rule["severity"], rule["message"]),
                )
                totals[rule["id"]] = cur.rowcount
                log(f"  {rule['id']:26} {rule['severity']:9} {cur.rowcount:>6,}")
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("""SELECT severity, count(*) FROM qc_exception
                           WHERE status = 'open' GROUP BY severity ORDER BY severity""")
            summary = dict(cur.fetchall())

    blocking = summary.get("critical", 0)
    log(f"con mo: {summary}")
    log(f"cong phat hanh: {'KHOA' if blocking else 'SAN SANG'} ({blocking} critical)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
