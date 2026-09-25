"""Data Operations API.

Quy trinh nam o docs/quy-trinh-chat-luong.md. Ba dieu rang buoc ca file
nay, doc truoc khi sua:

1. API nay KHONG sua so. Khong endpoint nao ghi vao fact_current. So sai
   thi mo ticket de team Data sua o nguon.
2. Vi pham QC la nghi ngo cua may — no khong tu khoa cong phat hanh.
   Nguoi chiu trach nhiem duyet bang phieu duyet, va ten ho nam trong
   ban ky.
3. Cai khoa cung chi con hai: ticket dang chan, va QC chua kiem lan nap
   hien tai. Ca hai deu khong phai chuyen y kien.
"""

import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import agent, bq_snapshot, rules as rules_file
from .auth import caller_email
from .authz import Principal, load_principal, scope_clause
from .db import db
from .settings import settings

app = FastAPI(title="Data Operations API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Allowlist ten cot duoc sap xep. Khong bao gio noi chuoi tu client vao SQL.
SORTABLE = {"deposit", "deposit_share", "institution", "year"}
NATURAL_KEY = ("year", "state", "institution_id")


def principal(request: Request) -> Principal:
    email = caller_email(request)
    with db() as conn:
        return load_principal(conn, email)


Me = Annotated[Principal, Depends(principal)]


def audit(cur, actor: str, action: str, entity: str, key: str,
          before: Any = None, after: Any = None) -> None:
    cur.execute(
        """INSERT INTO audit_log (actor, action, entity, entity_key, before, after)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (actor, action, entity, key,
         json.dumps(before) if before is not None else None,
         json.dumps(after) if after is not None else None),
    )


def run_job(job_name: str, env: dict[str, str] | None = None) -> tuple[bool, str]:
    """Kich hoat mot Cloud Run Job, tra ve (co chay khong, giai thich).

    KHONG nem exception: ca hai cho goi den day deu da ghi xong viec cua
    minh vao database. Goi duoc thi tot, khong goi duoc — chay local, chua
    deploy job, thieu quyen — thi cong viec van nam trong hang doi cho lan
    chay sau, va nguoi dung duoc noi ro thay vi mat trang.
    """
    if not settings.gcp_project_id:
        return False, "chua cau hinh GCP_PROJECT_ID — job khong duoc kich hoat tu dong"

    url = (f"https://run.googleapis.com/v2/projects/{settings.gcp_project_id}"
           f"/locations/{settings.region}/jobs/{job_name}:run")
    body: dict = {}
    if env:
        body = {"overrides": {"containerOverrides": [
            {"env": [{"name": k, "value": v} for k, v in env.items()]}]}}

    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        res = AuthorizedSession(creds).post(url, json=body, timeout=20)
    except Exception as exc:  # noqa: BLE001
        return False, f"khong goi duoc {job_name}: {exc}"

    if res.status_code >= 300:
        return False, f"Cloud Run tu choi {job_name}: {res.status_code} {res.text[:200]}"
    return True, res.json().get("name", "")


def encode_cursor(row: dict, sort: str) -> str:
    payload = {"s": row[sort], **{k: row[k] for k in NATURAL_KEY}}
    return base64.urlsafe_b64encode(json.dumps(payload, default=str).encode()).decode()


def decode_cursor(cur: str) -> dict:
    try:
        return json.loads(base64.urlsafe_b64decode(cur.encode()))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "cursor khong hop le") from exc


# ------------------------------------------------------------------ health

@app.get("/health")
def health() -> dict:
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute("SELECT version() AS v")
            server = cur.fetchone()["v"].split(",")[0]
        database = {"connected": True, "server": server}
    except Exception as exc:  # noqa: BLE001
        database = {"connected": False, "error": str(exc)}
    return {"status": "ok", "service": "dataops-api",
            "time": datetime.now(timezone.utc).isoformat(),
            "require_iap": settings.require_iap, "database": database}


@app.get("/api/me")
def me(p: Me) -> dict:
    return {"email": p.email, "display_name": p.display_name,
            "roles": sorted(p.roles),
            "scope_states": "tat ca" if p.unrestricted else sorted(p.scope_states),
            # Giao dien an bo chon danh tinh khi IAP da bat — luc do danh
            # tinh den tu JWT cua Google, khong doi duoc bang tay.
            "require_iap": settings.require_iap}


@app.get("/api/version")
def version() -> dict:
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT last_run_id, last_synced_at, last_row_count,
                              source_row_count, status, last_error
                       FROM sync_state WHERE id = 1""")
        row = cur.fetchone()
    if not row:
        return {"run_id": None, "note": "chua sync lan nao"}
    synced = row["last_synced_at"]
    age = (datetime.now(timezone.utc) - synced).total_seconds() if synced else None
    return {"run_id": row["last_run_id"],
            "last_synced_at": synced.isoformat() if synced else None,
            "age_seconds": round(age) if age is not None else None,
            "stale": age is not None and age > 1800,
            "row_count": row["last_row_count"], "source_row_count": row["source_row_count"],
            "status": row["status"], "error": row["last_error"]}


@app.get("/api/schema")
def schema() -> dict:
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT c.relname AS table_name, c.reltuples::bigint AS est_rows,
                              pg_size_pretty(pg_total_relation_size(c.oid)) AS size
                       FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname""")
        tables = cur.fetchall()
        for t in tables:
            if t["est_rows"] is None or t["est_rows"] < 0:
                cur.execute(f'SELECT count(*) AS n FROM "{t["table_name"]}"')
                t["est_rows"] = cur.fetchone()["n"]
        cur.execute("""SELECT column_name, data_type FROM information_schema.columns
                       WHERE table_schema='public' AND table_name='fact_current'
                       ORDER BY ordinal_position""")
        cols = cur.fetchall()
        cur.execute("""SELECT indexname FROM pg_indexes
                       WHERE tablename='fact_current' ORDER BY indexname""")
        idx = cur.fetchall()
    return {"tables": tables, "fact_current": {"columns": cols, "indexes": idx}}


# ------------------------------------------------------------------- facts

# Thu tu muc do, dung chung cho luoi du lieu va hop chi tiet vi pham: mot o
# co the vi pham nhieu luat cung luc, nhung tren luoi chi co cho cho MOT
# cham mau — cham do phai la muc nang nhat, khong phai luat gap dau tien.
SEVERITY_RANK = "CASE e.severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END"


@app.get("/api/facts")
def facts(
    p: Me,
    state: str | None = None,
    year: int | None = None,
    institution: str | None = None,
    sort: str = Query("deposit"),
    desc: bool = True,
    limit: int = Query(50, ge=1, le=500),
    cursor: str | None = None,
) -> dict:
    if sort not in SORTABLE:
        raise HTTPException(400, f"khong sap xep duoc theo '{sort}'; cho phep: {sorted(SORTABLE)}")

    # Pham vi ep tu database theo email — KHONG lay tu tham so client.
    scope_sql, scope_params = scope_clause(p, state, alias="f")
    where, params = ([scope_sql], list(scope_params)) if scope_sql else ([], [])

    if year:
        where.append("f.year = %s"); params.append(year)
    if institution:
        where.append("f.institution ILIKE %s"); params.append(f"{institution}%")

    # Keyset pagination: khong dung OFFSET, nen trang sau khong cham dan.
    op = "<" if desc else ">"
    if cursor:
        c = decode_cursor(cursor)
        where.append(
            f"(f.{sort}, f.year, f.state, f.institution_id) {op} (%s, %s, %s, %s)")
        params += [c["s"], c["year"], c["state"], c["institution_id"]]

    clause = f"WHERE {' AND '.join(w for w in where if w)}" if where else ""
    direction = "DESC" if desc else "ASC"

    # So doc ra la so cua nguon, khong hon khong kem: ung dung nay khong
    # sua so. O nao dang co ticket thi duoc danh dau de nguoi doc biet no
    # dang cho team Data sua, chu KHONG thay so.
    #
    # Vi pham QC dem bang LATERAL o vong ngoai, SAU khi LIMIT da cat: mot
    # trang 500 dong ton dung 500 lan tra ix_qc_key, chu khong phai mot
    # lan dem qua ca 1,2 trieu dong. Va chi dem — luat nao bi vi pham thi
    # /api/facts/violations tra ve luc nguoi dung bam vao cham do. Cot
    # message lap lai nguyen van o tung dong; nhet no vao moi trang la
    # phinh duong truyen cho thu hau het khong ai mo ra xem.
    sql = f"""
        WITH trang AS (
            SELECT f.year, f.state, f.institution_id, f.institution, f.run_id,
                   f.deposit, f.deposit_share, f.prev_deposit, f.prev_year,
                   t.id AS ticket_id, t.status AS ticket_status,
                   t.expected_value AS ticket_expected, t.blocking AS ticket_blocking
            FROM fact_current f
            LEFT JOIN ticket t
              ON t.year = f.year AND t.state = f.state
             AND t.institution_id = f.institution_id AND t.field = 'deposit'
             AND t.status IN ('open', 'awaiting_verify')
            {clause}
            ORDER BY f.{sort} {direction}, f.year {direction}, f.state {direction},
                     f.institution_id {direction}
            LIMIT %s
        )
        SELECT trang.*, v.n AS violations, v.severity AS violation_severity
        FROM trang
        LEFT JOIN LATERAL (
            SELECT count(*) AS n,
                   CASE WHEN count(*) = 0 THEN NULL
                        ELSE (ARRAY['critical','warning','info'])[min({SEVERITY_RANK})]
                   END AS severity
            FROM qc_exception e
            WHERE e.run_id = %s AND e.year = trang.year AND e.state = trang.state
              AND e.institution_id = trang.institution_id
        ) v ON true
        ORDER BY trang.{sort} {direction}, trang.year {direction},
                 trang.state {direction}, trang.institution_id {direction}
    """
    with db() as conn, conn.cursor() as cur:
        st = qc_state(cur)
        # Lan nap ma QC da kiem THAT. Lech voi lan nap dang hien thi la
        # chuyen binh thuong (vua sync xong, QC chua chay lai) — luc do cac
        # cham do la cua lan nap truoc, va giao dien phai noi ro dieu do
        # thay vi de nguoi doc tuong no dang noi ve so truoc mat.
        qc_run = st.get("qc_run_id")
        cur.execute(sql, [*params, limit + 1, qc_run])
        rows = cur.fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]

    return {"rows": rows, "limit": limit, "has_more": has_more,
            "next_cursor": encode_cursor(rows[-1], sort) if rows and has_more else None,
            "scope": "tat ca" if p.unrestricted else sorted(p.scope_states),
            "run_id": st.get("last_run_id"), "qc_run_id": qc_run,
            "qc_stale": qc_stale(st) is not None, "qc_stale_reason": qc_stale(st),
            "rules_version": st.get("rules_version"),
            "ruleset_version": st.get("ruleset_version")}


@app.get("/api/facts/violations")
def fact_violations(
    p: Me,
    year: int,
    state: str,
    institution_id: int,
    run_id: str | None = None,
) -> dict:
    """Vi pham cua DUNG MOT o — cham do tren luoi du lieu bam vao day.

    Tach khoi /api/facts co chu y: luoi chi can biet co hay khong, va nang
    den dau, de ve cham mau; con vi pham luat gi thi phai doc chu, ma doc
    thi moi lan chi doc mot o.

    Khong tra ve vi pham cap nhom (luat nao co institution_id NULL, vi du
    tong thi phan cua ca bang lech 100%) — nhung vi pham do khong thuoc ve
    rieng dong nao, dan len ca nghin dong cung mot canh bao la bao sai cho
    999 dong vo can. Chung nam o man hinh Vi pham luat.
    """
    state = state.upper()
    if not p.unrestricted and state not in p.scope_states:
        raise HTTPException(403, f"ban khong co pham vi tren bang {state}")

    with db() as conn, conn.cursor() as cur:
        st = qc_state(cur)
        target = run_id or st.get("qc_run_id")
        stale, reason = qc_stale(st) is not None, qc_stale(st)
        if not target:
            return {"run_id": None, "rows": [], "ticket": None,
                    "qc_stale": stale, "qc_stale_reason": reason,
                    "rules_version": st.get("rules_version")}

        cur.execute(
            f"""SELECT id, rule_id, severity, message, observed, created_at
                FROM qc_exception e
                WHERE e.run_id = %s AND e.year = %s AND e.state = %s
                  AND e.institution_id = %s
                ORDER BY {SEVERITY_RANK}, e.rule_id""",
            (target, year, state, institution_id))
        rows = cur.fetchall()

        # Ai bam vao cham do cung hoi ngay cau thu hai: "cai nay co ai lo
        # chua". Tra loi luon, de khong phai sang man hinh khac de biet.
        cur.execute(
            """SELECT id, title, status, blocking, expected_value
               FROM ticket
               WHERE year=%s AND state=%s AND institution_id=%s AND field='deposit'
                 AND status IN ('open','awaiting_verify')""",
            (year, state, institution_id))
        ticket = cur.fetchone()

    return {"run_id": target, "rows": rows, "ticket": ticket,
            "qc_stale": stale, "qc_stale_reason": reason,
            "rules_version": st.get("rules_version")}


# ------------------------------------------------------ van tay & vi pham

def qc_state(cur) -> dict:
    """Lan nap hien tai + lan QC gan nhat + version bo luat.

    Ba thu nay phai doc cung mot luc: ky mot lan nap MA QC chua kiem thi
    danh sach vi pham tren man hinh la cua lan nap truoc, va phieu duyet
    se noi ve mot thu khong con ton tai.
    """
    cur.execute("""SELECT s.last_run_id, s.last_row_count, s.source_run_ids,
                          s.qc_run_id, s.qc_checked_at, s.rules_version,
                          (SELECT version FROM qc_ruleset WHERE id = 1) AS ruleset_version
                   FROM sync_state s WHERE s.id = 1""")
    return cur.fetchone() or {}


def qc_stale(st: dict) -> str | None:
    """Vi sao danh sach vi pham dang hien KHONG phai cua du lieu + bo luat
    hien tai. None = QC da kiem dung lan nap nay, dung bo luat nay.

    Hai ly do, va P10 them ly do thu hai: bo luat vua duoc sua trong ung
    dung ma QC chua chay lai. Ky luc do la ky mot phieu duyet noi ve vi
    pham cua bo luat CU.
    """
    if not st.get("last_run_id"):
        return None
    if st.get("qc_run_id") != st["last_run_id"]:
        return "run"
    if st.get("ruleset_version") is not None and st.get("rules_version") != st["ruleset_version"]:
        return "rules"
    return None


def violations_of(cur, run_id: str) -> dict:
    """Bo vi pham cua MOT lan nap: dem theo luat, theo muc, va van tay.

    Van tay dung tong hash thay vi noi chuoi: tong khong phu thuoc thu tu
    va khong giu gi trong bo nho, nen no khong phinh ra theo so vi pham.
    Nho no ma phan biet duoc "van 3 o cu" voi "3 o khac" — hai thu nay
    tren giao dien trong het suc giong nhau.
    """
    cur.execute(
        """SELECT rule_id, severity, count(*) AS n FROM qc_exception
           WHERE run_id = %s GROUP BY rule_id, severity ORDER BY n DESC""", (run_id,))
    by_rule = cur.fetchall()
    cur.execute(
        """SELECT count(*) AS n,
                  coalesce(sum((('x' || substr(md5(
                      rule_id || '|' || coalesce(year::text,'') || '|' || coalesce(state,'') ||
                      '|' || coalesce(institution_id::text,'')
                  ), 1, 8))::bit(32)::int)::bigint), 0) AS h
           FROM qc_exception WHERE run_id = %s""", (run_id,))
    agg = cur.fetchone()
    by_severity: dict[str, int] = {}
    for r in by_rule:
        by_severity[r["severity"]] = by_severity.get(r["severity"], 0) + r["n"]
    return {
        "run_id": run_id,
        "total": agg["n"],
        "by_rule": by_rule,
        "by_severity": by_severity,
        "fingerprint": hashlib.md5(f"{agg['n']}:{agg['h']}".encode()).hexdigest(),
    }


def data_checksum(cur, source_run_ids: list[str] | None) -> str | None:
    """Van tay DU LIEU cua ban sap ky.

    Muc dich hep va ro: phat hien nguon bi sua TAI CHO duoi cung mot
    run_id. Khong phai chu ky chong gia mao — no chi can bat duoc thay
    doi, va phai chay duoc tren db-f1-micro voi 1,2 trieu dong, nen dung
    tong hash O(1) bo nho thay vi noi ca bang thanh mot chuoi.
    """
    if not source_run_ids:
        return None
    cur.execute(
        """SELECT count(*) AS n, coalesce(sum(deposit), 0) AS total,
                  coalesce(sum((('x' || substr(md5(
                      year::text || '|' || state || '|' || institution_id::text ||
                      '|' || deposit::text
                  ), 1, 8))::bit(32)::int)::bigint), 0) AS h
           FROM fact_current WHERE run_id = ANY(%s)""", (list(source_run_ids),))
    r = cur.fetchone()
    return hashlib.md5(f"{r['n']}:{r['total']}:{r['h']}".encode()).hexdigest()


def require_gate_open(cur) -> None:
    """Chan phat hanh. Dung mot cho, dung cho ca luc xin file lan luc tai.

    Cong co the khoa lai GIUA hai thao tac do — ai do vua mo mot ticket
    chan — nen kiem o ca hai dau, khong phai thua.
    """
    blockers = open_tickets(cur, only_blocking=True)
    if blockers:
        raise HTTPException(409, {
            "loi": "con ticket dang chan phat hanh",
            "so_ticket": len(blockers),
            "ticket": [{"id": t["id"], "title": t["title"]} for t in blockers[:20]],
        })


def open_tickets(cur, only_blocking: bool = False) -> list[dict]:
    """Ticket chua dong — TOAN CUC, khong loc theo pham vi.

    Co chu y: ticket chan ky la chuyen cua ca bo du lieu. Analyst Texas
    phai thay dung thu dang chan phat hanh ngay ca khi no nam o bang khac,
    y het cach cong phat hanh van luon toan cuc.
    """
    extra = " AND blocking" if only_blocking else ""
    cur.execute(
        f"""SELECT id, year, state, institution_id, institution, field, title, expected_value,
                   observed_at_open, last_observed, blocking, status, created_by,
                   created_at, marked_fixed_by, marked_fixed_at,
                   last_checked_run_id, last_checked_at, from_rule_id, evidence
            FROM ticket
            WHERE status IN ('open', 'awaiting_verify'){extra}
            ORDER BY blocking DESC, id""")
    return cur.fetchall()


# --------------------------------------------------------------- bo luat QC
#
# Tu P10 bo luat song trong Postgres (qc_rule / qc_ruleset /
# qc_ruleset_snapshot) va sua duoc ngay trong ung dung. Ba dieu giu nguyen:
#
# - Moi lan ghi thanh cong la MOT version moi, +1, cung transaction voi
#   snapshot toan bo bo luat va audit_log. Ban ky ghi version QC DA CHAY,
#   nen tai hien duoc bo luat da duyet.
# - Khong luu luat hong: cau truc kiem truoc, SQL chay thu trong
#   transaction chi doc ngay truoc khi ghi — khong tin ket qua preview
#   client gui len.
# - Luat la quy tac chung, khong theo pham vi bang: ai cung DOC duoc, chi
#   team_lead / admin SUA duoc.

EDITORS = ("team_lead", "admin")


class RuleBody(BaseModel):
    severity: str
    scope: list[str] | None = None
    message: str
    sql: str
    enabled: bool = True
    # Khoa lac quan: version bo luat nguoi sua dang nhin thay.
    expected_version: int


class RuleCreateBody(RuleBody):
    id: str


class RulePreviewBody(BaseModel):
    sql: str
    scope: list[str] | None = None


def _rule_json(r: dict) -> dict:
    """Luat dang JSON cho audit_log — before/after doc duoc bang mat."""
    return {k: r.get(k) for k in ("id", "severity", "scope", "message", "sql", "enabled")}


def _check_rule_or_422(rule: dict, *, check_id: bool) -> None:
    """Hai lop: cau truc, roi SQL chay that tren connection rieng, chi doc."""
    loi = rules_file.validate_rule(rule, check_id=check_id)
    if loi:
        raise HTTPException(422, {"errors": loi, "missing_columns": []})
    with db() as conn:
        res = rules_file.dry_run(conn, rule["sql"], rule["scope"], sample=0)
    if res["error"]:
        raise HTTPException(422, {"errors": [f"SQL loi: {res['error']}"], "missing_columns": []})
    if res["missing_columns"]:
        raise HTTPException(422, {
            "errors": [f"SQL thieu cot: {', '.join(res['missing_columns'])}"],
            "missing_columns": res["missing_columns"]})


def _lock_ruleset(cur, expected: int) -> int:
    """Khoa dong qc_ruleset toi het transaction, doi chieu version.

    Hai nguoi sua cung luc: nguoi sau nhan 409 kem ai vua sua, thay vi ghi
    de len thay doi cua nguoi truoc ma khong ai biet.
    """
    cur.execute("SELECT version, updated_by, updated_at FROM qc_ruleset WHERE id = 1 FOR UPDATE")
    st = cur.fetchone()
    if not st:
        raise HTTPException(503, "chua co bo luat — chay migration p10 (alembic upgrade head)")
    if st["version"] != expected:
        raise HTTPException(409, {
            "message": "bo luat da duoc nguoi khac sua — tai lai roi sua tiep",
            "current_version": st["version"], "expected_version": expected,
            "updated_by": st["updated_by"],
            "updated_at": st["updated_at"].isoformat() if st["updated_at"] else None})
    return st["version"]


def _bump(cur, actor: str, old: int, note: str) -> int:
    """Version +1 va snapshot toan bo bo luat SAU thay doi — cung transaction."""
    new = old + 1
    cur.execute("""UPDATE qc_ruleset SET version=%s, updated_by=%s, updated_at=now(), note=%s
                   WHERE id = 1""", (new, actor, note))
    snap = rules_file.snapshot_rows(rules_file.current_rules(cur))
    cur.execute("""INSERT INTO qc_ruleset_snapshot (version, rules, created_by, note)
                   VALUES (%s, %s, %s, %s)""", (new, json.dumps(snap), actor, note))
    return new


@app.get("/api/rules")
def rules(p: Me, version: int | None = Query(None, ge=1)) -> dict:
    """Bo luat — hien tai, hoac dung mot version cu (`?version=`) tu snapshot.

    Tra ve mot luc hai version, va ca hai deu can:

    - `version` — bo luat hien tai, thu se chay o lan QC ke tiep;
    - `applied_version` — bo luat QC da chay THAT tren lan nap hien tai.

    Lech nhau la chuyen binh thuong (vua sua, chua chay lai QC) nhung
    nguoi doc phai thay: khong thi ho doi chieu danh sach vi pham voi mot
    bo luat chua tung chay.
    """
    with db() as conn, conn.cursor() as cur:
        try:
            catalog = rules_file.load_from_db(cur, version)
        except Exception as exc:  # noqa: BLE001 — bang chua co = chua migrate
            raise HTTPException(503, f"chua doc duoc bo luat — da chay migration p10 chua? {exc}") from exc
        if catalog is None:
            raise HTTPException(404, f"khong co snapshot cho version {version}")
        st = qc_state(cur)

    applied = st.get("rules_version")
    current = st.get("ruleset_version")
    return {**catalog,
            "current_version": current,
            "applied_version": applied,
            "qc_run_id": st.get("qc_run_id"),
            "in_sync": applied is not None and applied == current,
            "can_edit": p.has(*EDITORS) and not catalog["snapshot"]}


@app.post("/api/rules/preview")
def preview_rule(body: RulePreviewBody, p: Me) -> dict:
    """Chay thu SQL cua luat: cot, so dong bat duoc (da ap scope), 20 dong
    mau. Khong ghi gi. Nguoi sua NHIN THAY luat bat duoc gi truoc khi luu."""
    p.require(*EDITORS)
    rule = rules_file.normalize({"id": "preview", "severity": "info", "message": "-",
                                 "sql": body.sql, "scope": body.scope})
    loi = [m for m in rules_file.validate_rule(rule, check_id=False)
           if "'sql'" in m or "'scope'" in m]
    if loi:
        raise HTTPException(422, {"errors": loi, "missing_columns": []})
    with db() as conn:
        return rules_file.dry_run(conn, rule["sql"], rule["scope"])


@app.post("/api/rules", status_code=201)
def create_rule(body: RuleCreateBody, p: Me) -> dict:
    p.require(*EDITORS)
    rule = rules_file.normalize(body.model_dump())
    _check_rule_or_422(rule, check_id=True)

    with db() as conn:
        with conn.cursor() as cur:
            old = _lock_ruleset(cur, body.expected_version)
            cur.execute("SELECT 1 FROM qc_rule WHERE id = %s", (rule["id"],))
            if cur.fetchone():
                raise HTTPException(409, {"message": f"da co luat '{rule['id']}'",
                                          "current_version": old})
            cur.execute("SELECT coalesce(max(sort_order), 0) + 10 AS n FROM qc_rule")
            order = cur.fetchone()["n"]
            cur.execute(
                f"""INSERT INTO qc_rule (id, severity, scope, message, sql, enabled,
                                         sort_order, created_by, updated_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING {rules_file.RULE_COLS}""",
                (rule["id"], rule["severity"], json.dumps(rule["scope"]) if rule["scope"] else None,
                 rule["message"], rule["sql"], body.enabled, order, p.email, p.email))
            row = cur.fetchone()
            new = _bump(cur, p.email, old, f"them {rule['id']}")
            audit(cur, p.email, "rule_create", "qc_rule", rule["id"], None,
                  {**_rule_json(row), "version": new})
        conn.commit()
    return {"rule": row, "version": new}


@app.put("/api/rules/{rule_id}")
def update_rule(rule_id: str, body: RuleBody, p: Me) -> dict:
    """Sua toan bo mot luat, ke ca bat/tat. `id` bat bien — xem models.QcRule."""
    p.require(*EDITORS)
    rule = rules_file.normalize({**body.model_dump(), "id": rule_id})
    _check_rule_or_422(rule, check_id=False)

    with db() as conn:
        with conn.cursor() as cur:
            old = _lock_ruleset(cur, body.expected_version)
            cur.execute(f"SELECT {rules_file.RULE_COLS} FROM qc_rule WHERE id = %s", (rule_id,))
            before = cur.fetchone()
            if not before:
                raise HTTPException(404, f"khong co luat '{rule_id}'")
            cur.execute(
                f"""UPDATE qc_rule SET severity=%s, scope=%s, message=%s, sql=%s, enabled=%s,
                                       updated_by=%s, updated_at=now()
                    WHERE id = %s RETURNING {rules_file.RULE_COLS}""",
                (rule["severity"], json.dumps(rule["scope"]) if rule["scope"] else None,
                 rule["message"], rule["sql"], body.enabled, p.email, rule_id))
            row = cur.fetchone()
            new = _bump(cur, p.email, old, f"sua {rule_id}")
            audit(cur, p.email, "rule_update", "qc_rule", rule_id,
                  _rule_json(before), {**_rule_json(row), "version": new})
        conn.commit()
    return {"rule": row, "version": new}


@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: str, p: Me, expected_version: int = Query(...)) -> dict:
    """Xoa han. Luat van con trong snapshot cu va audit_log; vi pham cua
    cac lan nap cu giu nguyen rule_id. Muon ngung tam thi tat, dung xoa."""
    p.require(*EDITORS)
    with db() as conn:
        with conn.cursor() as cur:
            old = _lock_ruleset(cur, expected_version)
            cur.execute(f"DELETE FROM qc_rule WHERE id = %s RETURNING {rules_file.RULE_COLS}",
                        (rule_id,))
            before = cur.fetchone()
            if not before:
                raise HTTPException(404, f"khong co luat '{rule_id}'")
            new = _bump(cur, p.email, old, f"xoa {rule_id}")
            audit(cur, p.email, "rule_delete", "qc_rule", rule_id,
                  _rule_json(before), {"version": new})
        conn.commit()
    return {"id": rule_id, "version": new}


@app.post("/api/rules/run-qc", status_code=202)
def run_qc(p: Me) -> dict:
    """Chay QC Runner ngay, khong cho Scheduler (5 phut).

    Cung khuon voi /api/rebuild: khong goi duoc job nghia la khong co gi
    xay ra — bao that bang 503. QC van tu chay lai o chu ky ke tiep vi no
    thay version bo luat da doi.
    """
    p.require(*EDITORS)
    triggered, note = run_job(settings.qc_job_name, {"FORCE_QC": "1"})
    if not triggered:
        raise HTTPException(503, note)
    with db() as conn:
        with conn.cursor() as cur:
            audit(cur, p.email, "qc_run", "qc_job", settings.qc_job_name, None,
                  {"operation": note})
        conn.commit()
    return {"job": settings.qc_job_name, "operation": note,
            "note": "QC Runner dang chay — banner lech version se tat khi xong"}


# -------------------------------------------------------------- vi pham QC

@app.get("/api/exceptions")
def exceptions(
    p: Me,
    severity: str | None = None,
    state: str | None = None,
    year: int | None = None,
    institution: str | None = None,
    run_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """Vi pham cua DUNG MOT lan nap — mac dinh la lan nap hien tai.

    Khong con bo loc trang thai: vi pham khong co trang thai nua. QC quet
    lai toan bo sau moi lan nap, nen danh sach nay luon la anh chup cua
    du lieu dang co, chu khong phai hop thu tich luy qua nhieu lan nap.
    """
    scope_sql, scope_params = scope_clause(p, state)
    with db() as conn, conn.cursor() as cur:
        st = qc_state(cur)
        target = run_id or st.get("qc_run_id") or st.get("last_run_id")
        if not target:
            return {"total": 0, "rows": [], "run_id": None,
                    "note": "chua co lan nap nao duoc kiem"}

        where, params = ["run_id = %s"], [target]
        if scope_sql:
            where.append(scope_sql); params += list(scope_params)
        if severity:
            where.append("severity = %s"); params.append(severity)
        if year:
            where.append("year = %s"); params.append(year)
        if institution:
            where.append("institution ILIKE %s"); params.append(f"{institution}%")

        cur.execute(f"SELECT count(*) AS n FROM qc_exception WHERE {' AND '.join(where)}", params)
        total = cur.fetchone()["n"]
        cur.execute(
            f"""SELECT id, run_id, rule_id, severity, year, state, institution_id, institution,
                       message, observed, created_at
                FROM qc_exception WHERE {' AND '.join(where)}
                ORDER BY severity, id LIMIT %s""",
            [*params, limit])
        rows = cur.fetchall()

    return {"total": total, "rows": rows, "run_id": target,
            "qc_stale": qc_stale(st) is not None, "qc_stale_reason": qc_stale(st),
            "rules_version": st.get("rules_version"),
            "ruleset_version": st.get("ruleset_version")}


# ----------------------------------------------------------------- ticket

class TicketBody(BaseModel):
    year: int
    state: str
    institution_id: int
    title: str = Field(min_length=5, description="loi la gi, noi cho nguoi khac doc")
    expected_value: int = Field(description="so DUNG — dieu kien nghiem thu QC doi chieu")
    evidence: str | None = None
    blocking: bool = True
    from_rule_id: str | None = None


@app.post("/api/tickets", status_code=201)
def create_ticket(body: TicketBody, p: Me) -> dict:
    """Bao mot loi cho team Data sua o nguon.

    Bat buoc co `expected_value` chu khong chi mo ta bang loi. Day la khac
    biet duy nhat giua mot ticket dong duoc va mot loi hua: QC o lan nap
    ke tiep doc so that len va doi chieu voi con so nay.
    """
    p.require("analyst", "team_lead", "admin")
    key = (body.year, body.state.upper(), body.institution_id)

    if not p.unrestricted and key[1] not in p.scope_states:
        raise HTTPException(403, f"ban khong co pham vi tren bang {key[1]}")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT deposit, institution FROM fact_current
                   WHERE year=%s AND state=%s AND institution_id=%s""", key)
            fact = cur.fetchone()
            if not fact:
                raise HTTPException(404, "khong co dong nao ung voi khoa nay trong lan nap hien tai")
            if int(fact["deposit"]) == body.expected_value:
                raise HTTPException(
                    400, f"so hien tai da la {body.expected_value} — khong co gi de sua")

            cur.execute(
                """SELECT id, status FROM ticket
                   WHERE year=%s AND state=%s AND institution_id=%s AND field='deposit'
                     AND status IN ('open','awaiting_verify')""", key)
            if dup := cur.fetchone():
                raise HTTPException(409, {
                    "loi": "o nay da co ticket dang mo",
                    "ticket_id": dup["id"], "status": dup["status"],
                })

            cur.execute(
                """INSERT INTO ticket
                       (year, state, institution_id, institution, field, title, expected_value,
                        observed_at_open, evidence, blocking, from_rule_id,
                        status, created_by)
                   VALUES (%s,%s,%s,%s,'deposit',%s,%s,%s,%s,%s,%s,'open',%s)
                   RETURNING id, created_at""",
                (*key, fact["institution"], body.title.strip(), str(body.expected_value),
                 str(fact["deposit"]), body.evidence, body.blocking, body.from_rule_id, p.email))
            t = cur.fetchone()
            audit(cur, p.email, "ticket_open", "ticket", str(t["id"]),
                  {"deposit": fact["deposit"]},
                  {"expected": body.expected_value, "blocking": body.blocking,
                   "title": body.title, "key": "/".join(map(str, key))})
        conn.commit()

    return {"id": t["id"], "status": "open", "key": list(key),
            "observed_at_open": fact["deposit"], "expected_value": body.expected_value,
            "blocking": body.blocking, "created_at": t["created_at"].isoformat()}


@app.get("/api/tickets")
def list_tickets(p: Me, status: str = Query("song"), limit: int = Query(100, ge=1, le=500)) -> dict:
    """`status=song` la ticket chua dong; con lai loc dung mot trang thai."""
    where, params = [], []
    if status == "song":
        where.append("status IN ('open','awaiting_verify')")
    elif status:
        where.append("status = %s"); params.append(status)

    scope_sql, scope_params = scope_clause(p, None)
    if scope_sql:
        where.append(scope_sql); params += list(scope_params)
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    with db() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) AS n FROM ticket {clause}", params)
        total = cur.fetchone()["n"]
        cur.execute(f"""SELECT * FROM ticket {clause}
                        ORDER BY (status='open') DESC, blocking DESC, id DESC
                        LIMIT %s""", [*params, limit])
        rows = cur.fetchall()
        blocking = len([t for t in open_tickets(cur, only_blocking=True)])
    return {"total": total, "rows": rows, "blocking_open": blocking,
            "can_set_blocking": p.has("team_lead", "admin")}


class TicketAction(BaseModel):
    action: str = Field(description="mark_fixed | set_blocking | cancel")
    blocking: bool | None = None
    reason: str = Field(min_length=3)


@app.patch("/api/tickets/{ticket_id}")
def update_ticket(ticket_id: int, body: TicketAction, p: Me) -> dict:
    """Ba thao tac nguoi lam duoc. DONG ticket khong nam trong so do.

    Dong la viec cua QC: no doc so that o lan nap ke tiep va doi chieu voi
    `expected_value`. Cho nguoi tu bam dong thi quay lai dung cho cu —
    trang thai noi da sua, du lieu thi chua.
    """
    if body.action not in {"mark_fixed", "set_blocking", "cancel"}:
        raise HTTPException(400, "action phai la mark_fixed | set_blocking | cancel")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ticket WHERE id = %s FOR UPDATE", (ticket_id,))
            t = cur.fetchone()
            if not t:
                raise HTTPException(404, f"khong co ticket {ticket_id}")
            if t["status"] in {"closed", "cancelled"}:
                raise HTTPException(409, f"ticket nay da o trang thai '{t['status']}'")
            if not p.unrestricted and t["state"] not in p.scope_states:
                raise HTTPException(403, f"ban khong co pham vi tren bang {t['state']}")

            if body.action == "mark_fixed":
                p.require("analyst", "team_lead", "admin")
                cur.execute(
                    """UPDATE ticket SET status='awaiting_verify', marked_fixed_by=%s,
                              marked_fixed_at=now() WHERE id=%s""", (p.email, ticket_id))
                new_status = "awaiting_verify"
                audit(cur, p.email, "ticket_mark_fixed", "ticket", str(ticket_id),
                      {"status": t["status"]}, {"status": new_status, "ly_do": body.reason})

            elif body.action == "set_blocking":
                # Doi mot ticket tu chan sang khong chan la mot quyet dinh
                # that, khong phai bo loc giao dien: no mo cong phat hanh.
                p.require("team_lead", "admin")
                if body.blocking is None:
                    raise HTTPException(400, "set_blocking thi phai gui kem blocking true/false")
                cur.execute("UPDATE ticket SET blocking=%s WHERE id=%s", (body.blocking, ticket_id))
                new_status = t["status"]
                audit(cur, p.email, "ticket_set_blocking", "ticket", str(ticket_id),
                      {"blocking": t["blocking"]},
                      {"blocking": body.blocking, "ly_do": body.reason})

            else:  # cancel — bao nham, khong phai loi
                if t["created_by"] != p.email:
                    p.require("team_lead", "admin")
                cur.execute(
                    """UPDATE ticket SET status='cancelled', closed_at=now() WHERE id=%s""",
                    (ticket_id,))
                new_status = "cancelled"
                audit(cur, p.email, "ticket_cancel", "ticket", str(ticket_id),
                      {"status": t["status"]}, {"status": new_status, "ly_do": body.reason})
        conn.commit()

    return {"id": ticket_id, "status": new_status,
            "blocking": body.blocking if body.action == "set_blocking" else t["blocking"]}


# ------------------------------------------------------------- AI Agent

class AgentChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # Noi tiep hoi thoai da co (server tra ve tu lan hoi truoc). Bo trong
    # thi mo phien moi — phien luu tren Postgres qua DatabaseSessionService,
    # xem app/agent/service.py.
    session_id: str | None = None


@app.post("/api/agent/chat")
async def agent_chat(body: AgentChatBody, p: Me) -> dict:
    """Hoi AI Agent (Google ADK) ve vi pham QC + ticket TRONG PHAM VI cua nguoi hoi.

    Agent chi doc — 4 tool cua no deu la SELECT, khong tool nao ghi/sua
    duoc gi. No khong dong ticket, khong ky ban, khong sua so: ba viec do
    van chi lam duoc qua co che da co (QC Runner, POST /api/release, mo
    ticket). Xem SYSTEM_PROMPT trong app/agent/root_agent.py cho day du
    gioi han, va app/agent/tools.py cho cach pham vi duoc ep tai tang tool.
    """
    reply, session_id = await agent.chat(p, body.message, body.session_id)
    return {"reply": reply, "session_id": session_id}


@app.get("/api/agent/usage")
def agent_usage(p: Me, force: bool = False) -> dict:
    """Token + uoc tinh chi phi Vertex AI tu dau thang (UTC).

    Doc tu Cloud Monitoring chu khong tu dem — xem app/agent/usage.py cho
    hai gioi han cua con so nay (la cua CA PROJECT, va tien chi la uoc
    tinh theo gia niem yet).

    `force=true` la nut "Lay lai so moi" trong modal chi phi tren man hinh
    Agent: bo qua cache 5 phut cua tien trinh de doc lai Monitoring ngay.
    No KHONG lam so realtime — metric token cua Vertex AI con tre khoang
    1-2 phut sau moi lenh goi, nen bam don chi ton them moi lan mot request
    Monitoring chu khong ra con so moi hon.

    Gioi han o team_lead/admin: day la chi phi ha tang, khong phai du lieu
    nghiep vu. Muon cho ca analyst xem thi bo dong require di — tool cua
    agent van tu ep pham vi, endpoint nay khong lam lo du lieu bang nao.

    Khong bao gio tra 5xx: goi khong duoc Monitoring thi tra
    {"available": false, "reason": ...} de o chi phi tren man hinh Agent
    im lang bien mat, khong lam hong cho chat.
    """
    p.require("team_lead", "admin")
    return agent.month_usage(force=force)


# ---------------------------------------------------------------- release

class ReleaseBody(BaseModel):
    label: str = Field(min_length=3)
    # Phieu duyet. Bat buoc khi ban ky con no: con vi pham luat, hoac con
    # ticket chua dong. Rong thi API tu choi — mon no phai co nguoi dung ten.
    approval_note: str = ""


@app.post("/api/release")
def release(body: ReleaseBody, p: Me) -> dict:
    """Ky mot ban phat hanh.

    QC khong co quyen phu quyet nguoi chiu trach nhiem: con vi pham luat
    thi van ky duoc, mien la team lead viet phieu duyet. Nhung hai thu
    van chan cung, va ca hai deu khong phai chuyen y kien:

    - Ticket dang CHAN: loi da duoc xac nhan bang bang chung, khong phai
      nghi ngo cua may. Muon ky thi go chan ticket — mot thao tac rieng,
      co ten nguoi, co ly do.
    - QC chua kiem lan nap hien tai: danh sach vi pham dang hien la cua
      lan nap truoc. Ky luc nay la ky mot thu minh chua nhin thay.

    Ky xong thi DU LIEU cung bi dong bang: bang fact tren BigQuery duoc
    chup thanh `snapshot_<epoch>` va ten bang ghi vao signed_version.
    Export chi doc tu snapshot do. BigQuery lech voi ban QC da kiem thi
    tu choi ky — xem app/bq_snapshot.py va docs/thiet-ke-ky-du-lieu.md.
    """
    p.require("team_lead", "admin")

    with db() as conn:
        with conn.cursor() as cur:
            blockers = open_tickets(cur, only_blocking=True)
            if blockers:
                raise HTTPException(409, {
                    "loi": "con ticket dang chan phat hanh",
                    "so_ticket": len(blockers),
                    "ticket": [{"id": t["id"], "title": t["title"],
                                "khoa": f"{t['state']}/{t['institution']}/{t['year']}",
                                "ky_vong": t["expected_value"],
                                "dang_doc_duoc": t["last_observed"] or t["observed_at_open"],
                                "status": t["status"]} for t in blockers[:20]],
                    "go_the_nao": "sua o nguon roi cho QC xac minh, hoac go chan tung ticket "
                                  "bang PATCH /api/tickets/{id} action=set_blocking",
                })

            st = qc_state(cur)
            if not st.get("last_run_id"):
                raise HTTPException(409, "chua co lan dong bo nao de ky")
            stale = qc_stale(st)
            if stale == "run":
                raise HTTPException(409, {
                    "loi": "QC chua kiem lan nap hien tai",
                    "lan_nap": st["last_run_id"],
                    "qc_da_kiem": st.get("qc_run_id"),
                    "y_nghia": "danh sach vi pham dang hien la cua lan nap truoc — "
                               "cho QC chay xong roi ky",
                })
            if stale == "rules":
                raise HTTPException(409, {
                    "loi": "QC chua chay duoi bo luat hien tai",
                    "bo_luat_hien_tai": st["ruleset_version"],
                    "qc_da_chay_duoi": st.get("rules_version"),
                    "y_nghia": "bo luat vua duoc sua — danh sach vi pham dang hien la cua "
                               "bo luat cu. Bam 'Chay QC ngay' trong hop Bo luat, hoac cho "
                               "QC tu chay (toi da 5 phut), roi ky",
                })

            v = violations_of(cur, st["last_run_id"])
            con_no = open_tickets(cur)
            note = body.approval_note.strip()
            if (v["total"] or con_no) and len(note) < 10:
                raise HTTPException(422, {
                    "loi": "ban nay con no — phai co phieu duyet",
                    "vi_pham": v["by_rule"], "so_vi_pham": v["total"],
                    "ticket_chua_dong": [t["id"] for t in con_no],
                    "can_gi": "gui approval_note noi ro vi sao van ky",
                })

            checksum = data_checksum(cur, st.get("source_run_ids"))

            # Dong bang DU LIEU truoc khi ghi ban ky. Thoi diem ky lam tron
            # ve giay vi ten snapshot la epoch giay — signed_at va ten bang
            # phai chi cung mot khoanh khac.
            signed_at = datetime.now(timezone.utc).replace(microsecond=0)
            try:
                snapshot = bq_snapshot.freeze(signed_at, st.get("source_run_ids") or [],
                                              checksum, body.label, p.email)
            except bq_snapshot.SnapshotError as exc:
                raise HTTPException(exc.status, exc.detail)

            # Dong bang danh sach lan nap du lieu. Thieu no thi Export Job
            # khong biet ban ky nay gom nhung gi, va se xuat ca nhung lan
            # nap den sau khi ky.
            try:
                cur.execute(
                    """INSERT INTO signed_version
                           (run_id, source_run_ids, label, row_count, checksum,
                            violations, violations_fingerprint, rules_version,
                            open_tickets, approval_note, signed_by, signed_at,
                            bq_snapshot)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING id, signed_at""",
                    (st["last_run_id"], json.dumps(st.get("source_run_ids")),
                     body.label, st["last_row_count"], checksum,
                     json.dumps({r["rule_id"]: r["n"] for r in v["by_rule"]}),
                     v["fingerprint"], st.get("rules_version"),
                     json.dumps([t["id"] for t in con_no]), note or None, p.email,
                     signed_at, snapshot))
                sv = cur.fetchone()
                audit(cur, p.email, "release", "signed_version", str(sv["id"]), None,
                      {"run_id": st["last_run_id"], "label": body.label,
                       "source_run_ids": st.get("source_run_ids"), "checksum": checksum,
                       "bq_snapshot": snapshot,
                       "so_vi_pham": v["total"], "van_tay_vi_pham": v["fingerprint"],
                       "rules_version": st.get("rules_version"),
                       "ticket_chua_dong": [t["id"] for t in con_no],
                       "phieu_duyet": note or None})
                conn.commit()
            except Exception:
                # Ban ky khong ghi duoc thi snapshot thanh mo coi — xoa di.
                bq_snapshot.drop(snapshot)
                raise

    return {"id": sv["id"], "run_id": st["last_run_id"], "label": body.label,
            "row_count": st["last_row_count"], "source_run_ids": st.get("source_run_ids"),
            "checksum": checksum, "bq_snapshot": snapshot, "violations": v["by_rule"],
            "violations_fingerprint": v["fingerprint"],
            "rules_version": st.get("rules_version"),
            "open_tickets": [t["id"] for t in con_no],
            "approval_note": note or None,
            "signed_at": sv["signed_at"].isoformat()}


@app.get("/api/gate")
def gate(p: Me) -> dict:
    """Trang thai cong phat hanh.

    Doi nghia so voi P3: vi pham luat khong con tu khoa cong. Chung la
    nghi ngo cua may, va nghi ngo thi de nguoi doc roi quyet. Cai khoa
    that chi con hai: ticket dang chan, va QC chua kiem lan nap hien tai.
    """
    with db() as conn, conn.cursor() as cur:
        st = qc_state(cur)
        run = st.get("qc_run_id") or st.get("last_run_id")
        v = violations_of(cur, run) if run else {"total": 0, "by_rule": [], "by_severity": {},
                                                 "fingerprint": None, "run_id": None}
        blockers = open_tickets(cur, only_blocking=True)
        con_no = open_tickets(cur)
        cur.execute("""SELECT id, label, run_id, signed_by, signed_at, checksum,
                              violations, violations_fingerprint, rules_version,
                              open_tickets, approval_note
                       FROM signed_version ORDER BY id DESC LIMIT 1""")
        last = cur.fetchone()

    why = qc_stale(st)
    stale = why is not None
    return {
        "locked": bool(blockers) or stale,
        "blocking_tickets": [{"id": t["id"], "title": t["title"],
                              "khoa": f"{t['state']}/{t['institution']}/{t['year']}",
                              "status": t["status"]} for t in blockers],
        "open_tickets": len(con_no),
        "violations": {"total": v["total"], "by_severity": v["by_severity"],
                       "by_rule": v["by_rule"], "fingerprint": v["fingerprint"]},
        # Con no thi ky duoc, nhung phai kem phieu duyet.
        "needs_approval": bool(v["total"] or con_no),
        "qc_stale": stale, "qc_stale_reason": why,
        "run_id": st.get("last_run_id"), "qc_run_id": st.get("qc_run_id"),
        "rules_version": st.get("rules_version"),
        "ruleset_version": st.get("ruleset_version"),
        "last_signed": last,
    }


# ---------------------------------------------------------------- exports

class ExportBody(BaseModel):
    format: str = "csv"


@app.post("/api/exports", status_code=202)
def create_export(body: ExportBody, p: Me) -> dict:
    """Xep hang mot yeu cau xuat file roi kich hoat Export Job.

    Ba thu duoc CHOT NGAY tai day chu khong doi luc job chay: ban ky nao,
    dinh dang gi, pham vi cua ai. Nguoi xin bi doi pham vi ngay hom sau
    thi file da phat van giai thich duoc bang dung mot dong trong bang.
    """
    if body.format not in {"csv", "xlsx"}:
        raise HTTPException(400, "format phai la csv hoac xlsx")

    with db() as conn:
        with conn.cursor() as cur:
            require_gate_open(cur)

            # File gui khach CHI duoc xuat tu ban da ky.
            cur.execute("""SELECT id, run_id, label, source_run_ids, bq_snapshot
                           FROM signed_version ORDER BY id DESC LIMIT 1""")
            sv = cur.fetchone()
            if not sv:
                raise HTTPException(409, "chua co ban nao duoc ky — khong co gi de xuat")
            if not sv["source_run_ids"]:
                raise HTTPException(
                    409,
                    f"ban ky '{sv['label']}' khong ghi lai duoc nhung lan nap nao nam trong do; "
                    "chay lai Sync Job roi ky lai truoc khi xuat file")
            # Ban ky truoc khi co snapshot: du lieu cua no khong con duoc
            # dong bang o dau ca. Xuat tu bang song la xuat so chua ai duyet.
            if not sv["bq_snapshot"]:
                raise HTTPException(
                    409,
                    f"ban ky '{sv['label']}' khong co snapshot BigQuery — ky lai de dong bang "
                    "du lieu truoc khi xuat file")

            scope = None if p.unrestricted else sorted(p.scope_states)
            cur.execute(
                """INSERT INTO export_job
                       (run_id, signed_version_id, format, scope_states, status, requested_by)
                   VALUES (%s, %s, %s, %s, 'pending', %s)
                   RETURNING id, created_at""",
                (sv["run_id"], sv["id"], body.format,
                 json.dumps(scope) if scope else None, p.email))
            job = cur.fetchone()
            audit(cur, p.email, "export_request", "export_job", str(job["id"]), None,
                  {"format": body.format, "signed_version_id": sv["id"], "scope": scope})
        conn.commit()

    triggered, note = run_job(settings.export_job_name, {"EXPORT_JOB_ID": str(job["id"])})

    return {"job_id": job["id"], "status": "pending",
            "created_at": job["created_at"].isoformat(),
            "signed_version": {"id": sv["id"], "label": sv["label"]},
            "format": body.format, "scope": scope,
            "triggered": triggered, "note": note}


@app.get("/api/exports/{job_id}")
def get_export(job_id: int, p: Me) -> dict:
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM export_job WHERE id = %s", (job_id,))
        job = cur.fetchone()
    if not job:
        raise HTTPException(404, f"khong co job {job_id}")
    if job["requested_by"] != p.email and not p.has("admin", "team_lead"):
        raise HTTPException(403, "khong phai job cua ban")
    return {"job_id": job["id"], "status": job["status"], "run_id": job["run_id"],
            "format": job["format"], "scope_states": job["scope_states"],
            "row_count": job["row_count"], "warning": job["warning"],
            "signed_version_id": job["signed_version_id"],
            "gcs_path": job["gcs_path"], "stamp_path": job["stamp_path"],
            "error": job["error"]}


# ---------------------------------------------------------------- options

@app.get("/api/options")
def options(p: Me) -> dict:
    """Gia tri cho thanh loc.

    Pham vi ap ca o day: analyst Texas khong duoc nhin thay ten bang khac
    trong dropdown — ro ri danh sach bang cung la ro ri.
    """
    scope_sql, scope_params = scope_clause(p, None)
    clause = f"WHERE {scope_sql}" if scope_sql else ""
    with db() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT DISTINCT state FROM fact_current {clause} ORDER BY state", scope_params)
        states = [r["state"] for r in cur.fetchall()]
        cur.execute(f"SELECT DISTINCT year FROM fact_current {clause} ORDER BY year DESC", scope_params)
        years = [r["year"] for r in cur.fetchall()]
    return {"states": states, "years": years,
            "sortable": sorted(SORTABLE)}


# --------------------------------------------------------------- dashboard

@app.get("/api/summary")
def summary(
    p: Me,
    state: str | None = None,
    year: int | None = None,
) -> dict:
    """So lieu cho dashboard. Mot lan goi thay vi sau lan goi roi rac.

    Bo loc tren thanh cong cu duoc ap vao phan dem dong va dem vi pham;
    cong phat hanh, ticket chan va ban da ky thi luon la toan cuc — ky la
    ky ca bo du lieu, khong ky rieng mot bang.
    """
    scope_sql, scope_params = scope_clause(p, state)
    where, params = ([scope_sql], list(scope_params)) if scope_sql else ([], [])
    if year:
        where.append("year = %s"); params.append(year)
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    with db() as conn, conn.cursor() as cur:
        cur.execute(f"""SELECT count(*) AS rows, min(year) AS year_min, max(year) AS year_max,
                               sum(deposit)::bigint AS total_deposit
                        FROM fact_current {clause}""", params)
        facts = cur.fetchone()

        st = qc_state(cur)
        run = st.get("qc_run_id") or st.get("last_run_id")

        # Vi pham: cung bo loc, nhung khoa cua vi pham co the NULL (luat
        # theo nhom nhu thi_phan_khong_tron_100 khong gan vao mot ten).
        extra = f" AND {' AND '.join(where)}" if where else ""
        base = ["run_id = %s"] if run else ["false"]
        vparams = ([run] if run else []) + params

        cur.execute(
            f"""SELECT severity, count(*) AS n FROM qc_exception
                WHERE {base[0]}{extra} GROUP BY severity""", vparams)
        by_severity = {r["severity"]: r["n"] for r in cur.fetchall()}

        cur.execute(
            f"""SELECT rule_id, severity, count(*) AS n FROM qc_exception
                WHERE {base[0]}{extra} GROUP BY rule_id, severity ORDER BY n DESC""", vparams)
        by_rule = cur.fetchall()

        cur.execute(
            f"""SELECT state, count(*) AS n FROM qc_exception
                WHERE {base[0]} AND state IS NOT NULL{extra}
                GROUP BY state ORDER BY n DESC LIMIT 12""", vparams)
        by_state = cur.fetchall()

        # So dong bi gan co = so khoa tu nhien khac nhau dang vi pham.
        cur.execute(
            f"""SELECT count(DISTINCT (year, state, institution_id)) AS n FROM qc_exception
                WHERE {base[0]} AND institution_id IS NOT NULL{extra}""", vparams)
        flagged = cur.fetchone()["n"]

        # Ticket: dem trong pham vi de nguoi dung thay phan viec cua minh,
        # nhung ticket CHAN thi dem toan cuc — no chan ca he thong.
        t_scope, t_params = scope_clause(p, state)
        t_clause = f" AND {t_scope}" if t_scope else ""
        cur.execute(
            f"""SELECT status, count(*) AS n FROM ticket
                WHERE status IN ('open','awaiting_verify'){t_clause}
                GROUP BY status""", t_params)
        tickets_by_status = {r["status"]: r["n"] for r in cur.fetchall()}
        blockers = open_tickets(cur, only_blocking=True)

        cur.execute("""SELECT id, label, run_id, row_count, signed_by, signed_at,
                              checksum, violations, violations_fingerprint,
                              rules_version, open_tickets, approval_note
                       FROM signed_version ORDER BY id DESC LIMIT 1""")
        signed = cur.fetchone()

        tickets_since = 0
        if signed:
            cur.execute("SELECT count(*) AS n FROM ticket WHERE created_at > %s",
                        (signed["signed_at"],))
            tickets_since = cur.fetchone()["n"]

        cur.execute("""SELECT last_run_id, last_synced_at, last_row_count, status
                       FROM sync_state WHERE id = 1""")
        sync = cur.fetchone()

        v_now = violations_of(cur, run) if run else None

    rows_now = sync["last_row_count"] if sync else None
    why = qc_stale(st)
    stale = why is not None
    return {
        "scope": "tat ca" if p.unrestricted else sorted(p.scope_states),
        "filters": {"state": state, "year": year},
        "facts": facts,
        "exceptions": {"open": sum(by_severity.values()), "by_severity": by_severity,
                       "by_rule": by_rule, "by_state": by_state,
                       "flagged_rows": flagged, "run_id": run},
        "tickets": {"open": tickets_by_status.get("open", 0),
                    "awaiting_verify": tickets_by_status.get("awaiting_verify", 0),
                    "blocking": len(blockers)},
        "gate": {"locked": bool(blockers) or stale, "blocking": len(blockers),
                 "qc_stale": stale, "qc_stale_reason": why,
                 "rules_version": st.get("rules_version"),
                 "ruleset_version": st.get("ruleset_version"),
                 "needs_approval": bool((v_now and v_now["total"]) or sum(tickets_by_status.values()))},
        "last_signed": signed,
        "delta": {
            # Chenh lech so voi ban da ky gan nhat — cai nguoi duyet can
            # biet truoc khi ky ban tiep theo.
            "run_changed": bool(signed and sync and signed["run_id"] != sync["last_run_id"]),
            "rows_signed": signed["row_count"] if signed else None,
            "rows_now": rows_now,
            "rows_delta": (rows_now - signed["row_count"]) if signed and rows_now else None,
            "tickets_since": tickets_since,
            # Van tay doi = tap vi pham da KHAC, du tong so co the y het.
            # Day la thu duy nhat phan biet "van 3 o cu" voi "3 o khac".
            "violations_changed": bool(
                signed and v_now and signed["violations_fingerprint"]
                and signed["violations_fingerprint"] != v_now["fingerprint"]),
            "violations_signed": signed["violations"] if signed else None,
            "violations_now": {r["rule_id"]: r["n"] for r in by_rule},
        },
        "sync": sync,
    }


# -------------------------------------------------------- chi tiet vi pham

@app.get("/api/exceptions/{exc_id}")
def exception_detail(exc_id: int, p: Me) -> dict:
    """Tat ca thu panel dieu tra can, trong MOT lan goi.

    Panel nay chi de DOC va de quyet dinh co mo ticket hay khong — khong
    con o nhap so nao o day. Vi vay no dat ban da ky gan nhat canh lan nap
    hien tai: cau hoi that su la "so nay co that su doi khong", chu khong
    phai "sua thanh bao nhieu".
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM qc_exception WHERE id = %s", (exc_id,))
        exc = cur.fetchone()
        if not exc:
            raise HTTPException(404, f"khong co vi pham {exc_id}")
        if not p.unrestricted and exc["state"] not in p.scope_states:
            raise HTTPException(403, f"ban khong co pham vi tren bang {exc['state']}")

        key = (exc["year"], exc["state"], exc["institution_id"])
        fact = ticket = None
        history: list = []
        if all(k is not None for k in key):
            cur.execute(
                """SELECT year, state, institution_id, institution, run_id, deposit, deposit_share,
                          prev_deposit, prev_year
                   FROM fact_current
                   WHERE year=%s AND state=%s AND institution_id=%s""", key)
            fact = cur.fetchone()
            cur.execute(
                """SELECT * FROM ticket
                   WHERE year=%s AND state=%s AND institution_id=%s AND field='deposit'
                   ORDER BY (status IN ('open','awaiting_verify')) DESC, id DESC LIMIT 1""", key)
            ticket = cur.fetchone()
            cur.execute(
                """SELECT actor, action, before, after, created_at FROM audit_log
                   WHERE entity_key = %s OR entity_key = %s ORDER BY id DESC LIMIT 10""",
                ("/".join(map(str, key)), str(ticket["id"]) if ticket else "-"))
            history = cur.fetchall()

        cur.execute("""SELECT id, label, run_id, row_count, signed_by, signed_at, checksum
                       FROM signed_version ORDER BY id DESC LIMIT 1""")
        signed = cur.fetchone()

    return {"exception": exc, "fact": fact, "ticket": ticket,
            "can_open_ticket": p.has("analyst", "team_lead", "admin"),
            "last_signed": signed, "history": history}


# --------------------------------------------------------------- versions

@app.get("/api/versions")
def versions(p: Me, limit: int = Query(50, ge=1, le=200)) -> dict:
    """Danh sach ban da ky — ai ky, luc nao, da gui cho ai."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id, run_id, label, row_count, signed_by, signed_at,
                              source_run_ids, checksum, violations,
                              violations_fingerprint, rules_version,
                              open_tickets, approval_note, bq_snapshot
                       FROM signed_version ORDER BY id DESC LIMIT %s""", (limit,))
        rows = cur.fetchall()
        if rows:
            cur.execute(
                """SELECT signed_version_id, customer, sent_by, sent_at, file_path
                   FROM versions_sent WHERE signed_version_id = ANY(%s)
                   ORDER BY sent_at DESC""", ([r["id"] for r in rows],))
            sent: dict[int, list] = {}
            for s in cur.fetchall():
                sent.setdefault(s.pop("signed_version_id"), []).append(s)
            for r in rows:
                r["sent"] = sent.get(r["id"], [])
    return {"rows": rows, "can_sign": p.has("team_lead", "admin")}


class SentBody(BaseModel):
    customer: str = Field(min_length=2)
    file_path: str | None = None


@app.post("/api/versions/{version_id}/sent", status_code=201)
def record_sent(version_id: int, body: SentBody, p: Me) -> dict:
    """Ghi nhan da gui ban nao cho khach nao. Khong xoa duoc — day la
    cau tra loi cho cau hoi 'so nay ho lay o dau ra'."""
    p.require("sale", "team_lead", "admin")
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, label FROM signed_version WHERE id = %s", (version_id,))
            sv = cur.fetchone()
            if not sv:
                raise HTTPException(404, f"khong co ban ky {version_id}")
            cur.execute(
                """INSERT INTO versions_sent (signed_version_id, customer, sent_by, file_path)
                   VALUES (%s,%s,%s,%s) RETURNING id, sent_at""",
                (version_id, body.customer.strip(), p.email, body.file_path))
            row = cur.fetchone()
            audit(cur, p.email, "send", "signed_version", str(version_id),
                  None, {"customer": body.customer, "file_path": body.file_path})
        conn.commit()
    return {"id": row["id"], "signed_version_id": version_id,
            "customer": body.customer, "sent_at": row["sent_at"].isoformat()}


# ---------------------------------------------------------- export: danh sach

@app.get("/api/exports")
def list_exports(p: Me, limit: int = Query(50, ge=1, le=200)) -> dict:
    """Job cua chinh minh. Admin va team lead nhin duoc tat ca."""
    where, params = ("", []) if p.has("admin", "team_lead") else ("WHERE requested_by = %s", [p.email])
    with db() as conn, conn.cursor() as cur:
        cur.execute(f"""SELECT e.id, e.run_id, e.status, e.requested_by, e.created_at,
                               e.finished_at, e.gcs_path, e.error, e.format,
                               e.scope_states, e.row_count, e.warning,
                               e.signed_version_id, v.label AS signed_label
                        FROM export_job e
                        LEFT JOIN signed_version v ON v.id = e.signed_version_id
                        {where.replace("requested_by", "e.requested_by")}
                        ORDER BY e.id DESC LIMIT %s""", [*params, limit])
        rows = cur.fetchall()
    return {"rows": rows}


@app.get("/api/exports/{job_id}/download")
def download_export(job_id: int, p: Me) -> dict:
    """Tra signed URL het han 15 phut.

    Hai lop chan truoc khi phat link: job phai xong, va cong phat hanh
    phai mo — file da sinh xong van khong duoc ra ngoai neu sau do co
    ngoai le nghiem trong moi.
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM export_job WHERE id = %s", (job_id,))
        job = cur.fetchone()
        if not job:
            raise HTTPException(404, f"khong co job {job_id}")
        if job["requested_by"] != p.email and not p.has("admin", "team_lead"):
            raise HTTPException(403, "khong phai job cua ban")
        require_gate_open(cur)

    if job["status"] != "done" or not job["gcs_path"]:
        raise HTTPException(409, f"job dang o trang thai '{job['status']}', chua co file")

    return {"job_id": job_id, "url": signed_url(job["gcs_path"]),
            "expires_in": 900, "gcs_path": job["gcs_path"]}


def signed_url(gcs_path: str) -> str:
    """Ky URL bang IAM SignBlob — service account tren Cloud Run khong
    co private key nen khong ky offline duoc."""
    try:
        import google.auth
        from google.auth.transport import requests as ga_requests
        from google.cloud import storage

        creds, _ = google.auth.default()
        creds.refresh(ga_requests.Request())
        blob = storage.Blob.from_string(gcs_path, client=storage.Client())
        return blob.generate_signed_url(
            version="v4", method="GET",
            expiration=timedelta(minutes=15),
            service_account_email=getattr(creds, "service_account_email", None),
            access_token=creds.token,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"chua ky duoc URL: {exc}") from exc


# ---------------------------------------------------------------- rebuild

@app.post("/api/rebuild", status_code=202)
def rebuild(p: Me) -> dict:
    """Nap lai tu nguon — KHAC voi lam moi bang.

    Lam moi bang chi goi lai API, doc ban sao Postgres, tuc thi.
    Nap lai chay han Sync Job: doc lai tu BigQuery, dung bang staging,
    doi ten. Ton thoi gian va cham vao nguon, nen chi team lead tro len
    bam duoc va giao dien phai hoi lai truoc.
    """
    p.require("team_lead", "admin")

    triggered, note = run_job(settings.sync_job_name)
    if not triggered:
        # Khac voi export: o day khong co gi nam trong hang doi ca, khong
        # goi duoc job nghia la khong co gi xay ra — phai bao that.
        raise HTTPException(503, note)

    with db() as conn:
        with conn.cursor() as cur:
            audit(cur, p.email, "rebuild", "sync_job", settings.sync_job_name, None,
                  {"operation": note})
        conn.commit()
    return {"job": settings.sync_job_name, "operation": note,
            "note": "Sync Job dang chay — banner do tuoi se doi khi xong"}


# ------------------------------------------------- nguoi dung & phan quyen
#
# Quyen nghiep vu nam trong Postgres (app_user + app_role), khong nam trong
# IAM — xem docs/runbook.md. Truoc day them nguoi phai vao psql go tay; gio
# co man hinh, nhung hai rang buoc duoi day thi giao dien khong duoc bo:
#
# - MOT nguoi MOT vai tro. Bang app_role chua duoc nhieu dong, nhung man
#   hinh chi cho chon mot — doi vai tro la THAY THE ca bo, khong cong don.
#   Cong don la cach de nhat de mot analyst giu lai pham vi cu sau khi bi
#   ha quyen.
# - Analyst BAT BUOC co it nhat mot bang. scope_states rong nghia la KHONG
#   GIOI HAN (xem authz.scope_clause), nen "quen chon" se cap nham toan bo
#   du lieu chu khong phai cap thieu.
#
# Email BAT BIEN sau khi tao: no la khoa dinh danh nguoi goi (auth.py) va
# duoc luu duoi dang chuoi trong audit_log.actor, ticket.created_by,
# signed_version.signed_by — khong co khoa ngoai nao de doi ten theo.

ROLES = ("admin", "team_lead", "analyst")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

USER_SELECT = """
    SELECT x.* FROM (
        SELECT DISTINCT ON (u.id)
               u.id, u.email, u.display_name, u.is_active, u.created_at,
               r.role, r.scope_states
        FROM app_user u LEFT JOIN app_role r ON r.user_id = u.id
        {where}
        ORDER BY u.id, r.id
    ) x ORDER BY x.email
"""


class UserCreate(BaseModel):
    email: str
    display_name: str | None = None
    role: str
    scope_states: list[str] | None = None


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: str
    scope_states: list[str] | None = None
    is_active: bool = True


def _users(cur, user_id: int | None = None) -> list[dict]:
    where = "WHERE u.id = %s" if user_id is not None else ""
    cur.execute(USER_SELECT.format(where=where), (user_id,) if user_id is not None else ())
    return cur.fetchall()


def _user_json(row: dict) -> dict:
    """Nguoi dung dang JSON cho audit_log — before/after doc duoc bang mat."""
    return {k: row.get(k) for k in ("email", "display_name", "role", "scope_states", "is_active")}


def _clean_role(role: str, scope: list[str] | None) -> tuple[str, list[str] | None]:
    if role not in ROLES:
        raise HTTPException(422, f"vai tro phai la mot trong: {', '.join(ROLES)}")
    states = sorted({s.strip().upper() for s in (scope or []) if s and s.strip()})
    if role != "analyst":
        # Team lead va admin khong gioi han bang. Giu NULL cho khoi hieu nham.
        return role, None
    if not states:
        raise HTTPException(422, "analyst phai duoc gan it nhat mot bang — "
                                 "de trong nghia la khong gioi han pham vi")
    return role, states


def _write_role(cur, user_id: int, role: str, states: list[str] | None) -> None:
    """Thay the toan bo vai tro cua mot nguoi. Xem ghi chu dau muc."""
    cur.execute("DELETE FROM app_role WHERE user_id = %s", (user_id,))
    cur.execute("INSERT INTO app_role (user_id, role, scope_states) VALUES (%s, %s, %s)",
                (user_id, role, json.dumps(states) if states else None))


@app.get("/api/users")
def list_users(p: Me) -> dict:
    """Danh sach tai khoan cho man hinh quan tri. Chi admin — nhu ca ba
    endpoint ghi ben duoi. Cap quyen la viec cua mot vai tro, doc xem ai
    dang co quyen gi cung vay.

    Bo chon danh tinh KHONG dung endpoint nay; no co duong rieng ben duoi.
    """
    p.require("admin")
    with db() as conn, conn.cursor() as cur:
        rows = _users(cur)
    return {"rows": rows, "roles": list(ROLES)}


@app.get("/api/users/switchable")
def switchable_users(p: Me) -> dict:
    """Danh sach cho bo chon danh tinh o goc tren ben phai — CHI che do dev.

    Tach khoi /api/users vi day la hai viec khac han nhau. /api/users la
    man hinh cap quyen: chi admin. Cai nay chi ton tai khi
    REQUIRE_IAP=false, tuc la luc danh tinh von KHONG duoc xac thuc — ai
    cung tu xung duoc bang header X-Dev-User, khong co quyen nao de bao ve
    o day. Doi lai, no bat buoc phai mo cho moi vai tro: doi sang analyst
    mot lan roi khong doi lai duoc thi ban demo coi nhu het.

    Bat IAP len thi 404 — bo chon luc do cung da bi khoa, va danh sach
    nhan su chi con di qua /api/users cua admin.
    """
    if settings.require_iap:
        raise HTTPException(404, "bo chon danh tinh chi co o che do dev")
    with db() as conn, conn.cursor() as cur:
        rows = _users(cur)
    # Chi nhung gi bo chon ve ra. Khong tra id, khong tra created_at —
    # chung khong dung vao viec gi ngoai man hinh quan tri.
    return {"rows": [{k: u[k] for k in ("email", "display_name", "role", "scope_states")}
                     for u in rows if u["is_active"]]}


@app.post("/api/users", status_code=201)
def create_user(body: UserCreate, p: Me) -> dict:
    p.require("admin")
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, f"email khong hop le: {email or '(de trong)'}")
    role, states = _clean_role(body.role, body.scope_states)

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM app_user WHERE lower(email) = %s", (email,))
            if cur.fetchone():
                raise HTTPException(409, f"da co tai khoan {email}")
            cur.execute("""INSERT INTO app_user (email, display_name, is_active)
                           VALUES (%s, %s, true) RETURNING id""",
                        (email, (body.display_name or "").strip() or None))
            uid = cur.fetchone()["id"]
            _write_role(cur, uid, role, states)
            row = _users(cur, uid)[0]
            audit(cur, p.email, "user_create", "app_user", email, None, _user_json(row))
        conn.commit()
    return row


@app.put("/api/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, p: Me) -> dict:
    """Sua ten hien thi, vai tro, pham vi, bat/tat. Email khong doi duoc."""
    p.require("admin")
    role, states = _clean_role(body.role, body.scope_states)

    with db() as conn:
        with conn.cursor() as cur:
            found = _users(cur, user_id)
            if not found:
                raise HTTPException(404, f"khong co tai khoan {user_id}")
            before = found[0]
            # Tu ha quyen chinh minh la mot cu bam khong go lai duoc: mat
            # quyen admin thi mat luon man hinh nay. Admin khac van lam duoc.
            if before["email"] == p.email and (role != "admin" or not body.is_active):
                raise HTTPException(409, "khong tu ha quyen hoac tu vo hieu hoa chinh minh — "
                                         "nho mot admin khac lam")
            cur.execute("""UPDATE app_user SET display_name = %s, is_active = %s
                           WHERE id = %s""",
                        ((body.display_name or "").strip() or None, body.is_active, user_id))
            _write_role(cur, user_id, role, states)
            row = _users(cur, user_id)[0]
            audit(cur, p.email, "user_update", "app_user", before["email"],
                  _user_json(before), _user_json(row))
        conn.commit()
    return row


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, p: Me) -> dict:
    """Xoa han tai khoan (app_role xoa theo CASCADE).

    Muon giu dau vet nguoi nay tung la ai thi TAT (is_active=false) chu
    dung xoa — xem docs/runbook.md. Ban ghi truoc khi xoa nam trong
    audit_log, con ticket va ban ky van giu nguyen email vi chung luu chuoi.
    """
    p.require("admin")
    with db() as conn:
        with conn.cursor() as cur:
            found = _users(cur, user_id)
            if not found:
                raise HTTPException(404, f"khong co tai khoan {user_id}")
            before = found[0]
            if before["email"] == p.email:
                raise HTTPException(409, "khong tu xoa chinh minh")
            cur.execute("DELETE FROM app_user WHERE id = %s", (user_id,))
            audit(cur, p.email, "user_delete", "app_user", before["email"],
                  _user_json(before), None)
        conn.commit()
    return {"id": user_id, "email": before["email"]}
