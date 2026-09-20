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


SEVERITIES = {"critical", "warning", "info"}


def log(msg: str) -> None:
    print(f"[qc] {msg}", flush=True)


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


def main() -> int:
    if not RULES_PATH.exists():
        log(f"khong thay file luat: {RULES_PATH}")
        return 1

    config = yaml.safe_load(RULES_PATH.read_text())
    rules = config["rules"]

    if loi := validate(rules):
        log(f"file luat co {len(loi)} loi — KHONG chay luat nao:")
        for m in loi:
            log(f"  - {m}")
        return 1
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
                where, scope_params = scope_filter(rule)
                cur.execute(
                    f"""
                    INSERT INTO qc_exception
                        (run_id, rule_id, severity, year, state, gender, name, message, observed, status)
                    SELECT %s, %s, %s, x.year, x.state, x.gender, x.name, %s, x.observed, 'open'
                    FROM ({rule['sql']}) x
                    {where}
                    """,
                    (run_id, rule["id"], rule["severity"], rule["message"], *scope_params),
                )
                totals[rule["id"]] = cur.rowcount
                pham_vi = f" [{','.join(rule['scope'])}]" if rule.get("scope") else ""
                log(f"  {rule['id']:26} {rule['severity']:9} {cur.rowcount:>6,}{pham_vi}")
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
