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
from pathlib import Path

import psycopg
import yaml

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dataops:dataops@localhost:5432/dataops")
RULES_PATH = Path(os.getenv("RULES_PATH", "/srv/rules/rules.yaml"))


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
                              t.state, t.gender, t.year, t.name, f.number
                       FROM ticket t
                       LEFT JOIN fact_current f
                         ON f.year = t.year AND f.state = t.state
                        AND f.gender = t.gender AND f.name = t.name
                       WHERE t.status IN ('open', 'awaiting_verify')
                       ORDER BY t.id""")
        rows = cur.fetchall()

    dem = {"dong": 0, "bat_lai": 0, "con_mo": 0}
    with conn.cursor() as cur:
        for tid, status, expected, blocking, state, gender, year, name, number in rows:
            quan_sat = None if number is None else str(number)
            khoa = f"{state}/{gender}/{year}/{name}"

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
                        (run_id, rule_id, severity, year, state, gender, name, message, observed)
                    SELECT %s, %s, %s, x.year, x.state, x.gender, x.name, %s, x.observed
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
