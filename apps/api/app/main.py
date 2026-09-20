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
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
SORTABLE = {"number", "market_share", "name", "year"}
NATURAL_KEY = ("year", "state", "gender", "name")


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

@app.get("/api/facts")
def facts(
    p: Me,
    state: str | None = None,
    year: int | None = None,
    gender: str | None = None,
    name: str | None = None,
    sort: str = Query("number"),
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
    if gender:
        where.append("f.gender = %s"); params.append(gender.upper())
    if name:
        where.append("f.name ILIKE %s"); params.append(f"{name}%")

    # Keyset pagination: khong dung OFFSET, nen trang sau khong cham dan.
    op = "<" if desc else ">"
    if cursor:
        c = decode_cursor(cursor)
        where.append(
            f"(f.{sort}, f.year, f.state, f.gender, f.name) {op} (%s, %s, %s, %s, %s)")
        params += [c["s"], c["year"], c["state"], c["gender"], c["name"]]

    clause = f"WHERE {' AND '.join(w for w in where if w)}" if where else ""
    direction = "DESC" if desc else "ASC"

    # So doc ra la so cua nguon, khong hon khong kem: ung dung nay khong
    # sua so. O nao dang co ticket thi duoc danh dau de nguoi doc biet no
    # dang cho team Data sua, chu KHONG thay so.
    sql = f"""
        SELECT f.year, f.state, f.gender, f.name, f.run_id,
               f.number, f.market_share, f.prev_number, f.prev_year,
               t.id AS ticket_id, t.status AS ticket_status,
               t.expected_value AS ticket_expected, t.blocking AS ticket_blocking
        FROM fact_current f
        LEFT JOIN ticket t
          ON t.year = f.year AND t.state = f.state
         AND t.gender = f.gender AND t.name = f.name AND t.field = 'number'
         AND t.status IN ('open', 'awaiting_verify')
        {clause}
        ORDER BY f.{sort} {direction}, f.year {direction}, f.state {direction},
                 f.gender {direction}, f.name {direction}
        LIMIT %s
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute(sql, [*params, limit + 1])
        rows = cur.fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]

    return {"rows": rows, "limit": limit, "has_more": has_more,
            "next_cursor": encode_cursor(rows[-1], sort) if rows and has_more else None,
            "scope": "tat ca" if p.unrestricted else sorted(p.scope_states)}


# ------------------------------------------------------ van tay & vi pham

def qc_state(cur) -> dict:
    """Lan nap hien tai + lan QC gan nhat + version bo luat.

    Ba thu nay phai doc cung mot luc: ky mot lan nap MA QC chua kiem thi
    danh sach vi pham tren man hinh la cua lan nap truoc, va phieu duyet
    se noi ve mot thu khong con ton tai.
    """
    cur.execute("""SELECT last_run_id, last_row_count, source_run_ids,
                          qc_run_id, qc_checked_at, rules_version
                   FROM sync_state WHERE id = 1""")
    return cur.fetchone() or {}


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
                      '|' || coalesce(gender,'') || '|' || coalesce(name,'')
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
        """SELECT count(*) AS n, coalesce(sum(number), 0) AS total,
                  coalesce(sum((('x' || substr(md5(
                      year::text || '|' || state || '|' || gender || '|' || name ||
                      '|' || number::text
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
        f"""SELECT id, year, state, gender, name, field, title, expected_value,
                   observed_at_open, last_observed, blocking, status, created_by,
                   created_at, marked_fixed_by, marked_fixed_at,
                   last_checked_run_id, last_checked_at, from_rule_id, evidence
            FROM ticket
            WHERE status IN ('open', 'awaiting_verify'){extra}
            ORDER BY blocking DESC, id""")
    return cur.fetchall()


# -------------------------------------------------------------- vi pham QC

@app.get("/api/exceptions")
def exceptions(
    p: Me,
    severity: str | None = None,
    state: str | None = None,
    year: int | None = None,
    gender: str | None = None,
    name: str | None = None,
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
        if gender:
            where.append("gender = %s"); params.append(gender.upper())
        if name:
            where.append("name ILIKE %s"); params.append(f"{name}%")

        cur.execute(f"SELECT count(*) AS n FROM qc_exception WHERE {' AND '.join(where)}", params)
        total = cur.fetchone()["n"]
        cur.execute(
            f"""SELECT id, run_id, rule_id, severity, year, state, gender, name,
                       message, observed, created_at
                FROM qc_exception WHERE {' AND '.join(where)}
                ORDER BY severity, id LIMIT %s""",
            [*params, limit])
        rows = cur.fetchall()

    return {"total": total, "rows": rows, "run_id": target,
            "qc_stale": bool(st.get("last_run_id") and st.get("qc_run_id") != st.get("last_run_id")),
            "rules_version": st.get("rules_version")}


# ----------------------------------------------------------------- ticket

class TicketBody(BaseModel):
    year: int
    state: str
    gender: str
    name: str
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
    key = (body.year, body.state.upper(), body.gender.upper(), body.name)

    if not p.unrestricted and key[1] not in p.scope_states:
        raise HTTPException(403, f"ban khong co pham vi tren bang {key[1]}")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT number FROM fact_current
                   WHERE year=%s AND state=%s AND gender=%s AND name=%s""", key)
            fact = cur.fetchone()
            if not fact:
                raise HTTPException(404, "khong co dong nao ung voi khoa nay trong lan nap hien tai")
            if int(fact["number"]) == body.expected_value:
                raise HTTPException(
                    400, f"so hien tai da la {body.expected_value} — khong co gi de sua")

            cur.execute(
                """SELECT id, status FROM ticket
                   WHERE year=%s AND state=%s AND gender=%s AND name=%s AND field='number'
                     AND status IN ('open','awaiting_verify')""", key)
            if dup := cur.fetchone():
                raise HTTPException(409, {
                    "loi": "o nay da co ticket dang mo",
                    "ticket_id": dup["id"], "status": dup["status"],
                })

            cur.execute(
                """INSERT INTO ticket
                       (year, state, gender, name, field, title, expected_value,
                        observed_at_open, evidence, blocking, from_rule_id,
                        status, created_by)
                   VALUES (%s,%s,%s,%s,'number',%s,%s,%s,%s,%s,%s,'open',%s)
                   RETURNING id, created_at""",
                (*key, body.title.strip(), str(body.expected_value), str(fact["number"]),
                 body.evidence, body.blocking, body.from_rule_id, p.email))
            t = cur.fetchone()
            audit(cur, p.email, "ticket_open", "ticket", str(t["id"]),
                  {"number": fact["number"]},
                  {"expected": body.expected_value, "blocking": body.blocking,
                   "title": body.title, "key": "/".join(map(str, key))})
        conn.commit()

    return {"id": t["id"], "status": "open", "key": list(key),
            "observed_at_open": fact["number"], "expected_value": body.expected_value,
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
                                "khoa": f"{t['state']}/{t['gender']}/{t['year']}/{t['name']}",
                                "ky_vong": t["expected_value"],
                                "dang_doc_duoc": t["last_observed"] or t["observed_at_open"],
                                "status": t["status"]} for t in blockers[:20]],
                    "go_the_nao": "sua o nguon roi cho QC xac minh, hoac go chan tung ticket "
                                  "bang PATCH /api/tickets/{id} action=set_blocking",
                })

            st = qc_state(cur)
            if not st.get("last_run_id"):
                raise HTTPException(409, "chua co lan dong bo nao de ky")
            if st.get("qc_run_id") != st["last_run_id"]:
                raise HTTPException(409, {
                    "loi": "QC chua kiem lan nap hien tai",
                    "lan_nap": st["last_run_id"],
                    "qc_da_kiem": st.get("qc_run_id"),
                    "y_nghia": "danh sach vi pham dang hien la cua lan nap truoc — "
                               "cho QC chay xong roi ky",
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

            # Dong bang danh sach lan nap du lieu. Thieu no thi Export Job
            # khong biet ban ky nay gom nhung gi, va se xuat ca nhung lan
            # nap den sau khi ky.
            cur.execute(
                """INSERT INTO signed_version
                       (run_id, source_run_ids, label, row_count, checksum,
                        violations, violations_fingerprint, rules_version,
                        open_tickets, approval_note, signed_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id, signed_at""",
                (st["last_run_id"], json.dumps(st.get("source_run_ids")),
                 body.label, st["last_row_count"], checksum,
                 json.dumps({r["rule_id"]: r["n"] for r in v["by_rule"]}),
                 v["fingerprint"], st.get("rules_version"),
                 json.dumps([t["id"] for t in con_no]), note or None, p.email))
            sv = cur.fetchone()
            audit(cur, p.email, "release", "signed_version", str(sv["id"]), None,
                  {"run_id": st["last_run_id"], "label": body.label,
                   "source_run_ids": st.get("source_run_ids"), "checksum": checksum,
                   "so_vi_pham": v["total"], "van_tay_vi_pham": v["fingerprint"],
                   "rules_version": st.get("rules_version"),
                   "ticket_chua_dong": [t["id"] for t in con_no],
                   "phieu_duyet": note or None})
        conn.commit()

    return {"id": sv["id"], "run_id": st["last_run_id"], "label": body.label,
            "row_count": st["last_row_count"], "source_run_ids": st.get("source_run_ids"),
            "checksum": checksum, "violations": v["by_rule"],
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

    stale = bool(st.get("last_run_id") and st.get("qc_run_id") != st.get("last_run_id"))
    return {
        "locked": bool(blockers) or stale,
        "blocking_tickets": [{"id": t["id"], "title": t["title"],
                              "khoa": f"{t['state']}/{t['gender']}/{t['year']}/{t['name']}",
                              "status": t["status"]} for t in blockers],
        "open_tickets": len(con_no),
        "violations": {"total": v["total"], "by_severity": v["by_severity"],
                       "by_rule": v["by_rule"], "fingerprint": v["fingerprint"]},
        # Con no thi ky duoc, nhung phai kem phieu duyet.
        "needs_approval": bool(v["total"] or con_no),
        "qc_stale": stale, "run_id": st.get("last_run_id"), "qc_run_id": st.get("qc_run_id"),
        "rules_version": st.get("rules_version"),
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
            cur.execute("""SELECT id, run_id, label, source_run_ids
                           FROM signed_version ORDER BY id DESC LIMIT 1""")
            sv = cur.fetchone()
            if not sv:
                raise HTTPException(409, "chua co ban nao duoc ky — khong co gi de xuat")
            if not sv["source_run_ids"]:
                raise HTTPException(
                    409,
                    f"ban ky '{sv['label']}' khong ghi lai duoc nhung lan nap nao nam trong do; "
                    "chay lai Sync Job roi ky lai truoc khi xuat file")

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
    return {"states": states, "years": years, "genders": ["F", "M"],
            "sortable": sorted(SORTABLE)}


# --------------------------------------------------------------- dashboard

@app.get("/api/summary")
def summary(
    p: Me,
    state: str | None = None,
    year: int | None = None,
    gender: str | None = None,
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
    if gender:
        where.append("gender = %s"); params.append(gender.upper())
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    with db() as conn, conn.cursor() as cur:
        cur.execute(f"""SELECT count(*) AS rows, min(year) AS year_min, max(year) AS year_max,
                               sum(number)::bigint AS total_number
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
            f"""SELECT count(DISTINCT (year, state, gender, name)) AS n FROM qc_exception
                WHERE {base[0]} AND name IS NOT NULL{extra}""", vparams)
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
    stale = bool(st.get("last_run_id") and st.get("qc_run_id") != st.get("last_run_id"))
    return {
        "scope": "tat ca" if p.unrestricted else sorted(p.scope_states),
        "filters": {"state": state, "year": year, "gender": gender},
        "facts": facts,
        "exceptions": {"open": sum(by_severity.values()), "by_severity": by_severity,
                       "by_rule": by_rule, "by_state": by_state,
                       "flagged_rows": flagged, "run_id": run},
        "tickets": {"open": tickets_by_status.get("open", 0),
                    "awaiting_verify": tickets_by_status.get("awaiting_verify", 0),
                    "blocking": len(blockers)},
        "gate": {"locked": bool(blockers) or stale, "blocking": len(blockers),
                 "qc_stale": stale,
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

        key = (exc["year"], exc["state"], exc["gender"], exc["name"])
        fact = ticket = None
        history: list = []
        if all(k is not None for k in key):
            cur.execute(
                """SELECT year, state, gender, name, run_id, number, market_share,
                          prev_number, prev_year
                   FROM fact_current
                   WHERE year=%s AND state=%s AND gender=%s AND name=%s""", key)
            fact = cur.fetchone()
            cur.execute(
                """SELECT * FROM ticket
                   WHERE year=%s AND state=%s AND gender=%s AND name=%s AND field='number'
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
                              open_tickets, approval_note
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
