"""Data Operations API — P3: phan quyen, override, cong phat hanh."""

import base64
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
    # alias "f" bat buoc vi cau truy van JOIN sang fact_override.
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

    sql = f"""
        SELECT f.year, f.state, f.gender, f.name, f.run_id,
               f.number AS number_raw, f.market_share, f.prev_number, f.prev_year,
               o.new_value, o.reason AS override_reason,
               o.created_by AS override_by, COALESCE(o.version, 0) AS override_version
        FROM fact_current f
        LEFT JOIN fact_override o
          ON o.year = f.year AND o.state = f.state
         AND o.gender = f.gender AND o.name = f.name AND o.field = 'number'
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

    for r in rows:
        # So hien thi = so da sua neu co override, khong thi lay so goc.
        r["number"] = int(r.pop("new_value")) if r["new_value"] is not None else r["number_raw"]
        r["overridden"] = r["number"] != r["number_raw"]

    return {"rows": rows, "limit": limit, "has_more": has_more,
            "next_cursor": encode_cursor(rows[-1], sort) if rows and has_more else None,
            "scope": "tat ca" if p.unrestricted else sorted(p.scope_states)}


# -------------------------------------------------------------- exceptions

@app.get("/api/exceptions")
def exceptions(
    p: Me,
    status: str = Query("open"),
    severity: str | None = None,
    state: str | None = None,
    year: int | None = None,
    gender: str | None = None,
    name: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    scope_sql, scope_params = scope_clause(p, state)
    where, params = ["status = %s"], [status]
    if scope_sql:
        where.append(scope_sql); params += list(scope_params)
    if severity:
        where.append("severity = %s"); params.append(severity)
    # Cung bo loc voi thanh loc chung cua giao dien.
    if year:
        where.append("year = %s"); params.append(year)
    if gender:
        where.append("gender = %s"); params.append(gender.upper())
    if name:
        where.append("name ILIKE %s"); params.append(f"{name}%")

    with db() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) AS n FROM qc_exception WHERE {' AND '.join(where)}", params)
        total = cur.fetchone()["n"]
        cur.execute(
            f"""SELECT id, run_id, rule_id, severity, year, state, gender, name,
                       message, observed, status, created_at
                FROM qc_exception WHERE {' AND '.join(where)}
                ORDER BY severity, id LIMIT %s""",
            [*params, limit])
        rows = cur.fetchall()
    return {"total": total, "rows": rows}


class ExceptionAction(BaseModel):
    action: str = Field(description="apply | park | send_back")
    new_value: int | None = None
    reason: str = Field(min_length=3)
    # Khoa lac quan: version cua override ma client dang nhin thay.
    expected_version: int = 0


@app.patch("/api/exceptions/{exc_id}")
def resolve_exception(exc_id: int, body: ExceptionAction, p: Me) -> dict:
    if body.action not in {"apply", "park", "send_back"}:
        raise HTTPException(400, "action phai la apply | park | send_back")
    if body.action == "apply" and body.new_value is None:
        raise HTTPException(400, "apply thi phai co new_value")

    with db() as conn:
        # Toan bo thao tac nam trong MOT transaction: ghi override, dong
        # ngoai le va ghi audit cung song cung chet.
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM qc_exception WHERE id = %s FOR UPDATE", (exc_id,))
            exc = cur.fetchone()
            if not exc:
                raise HTTPException(404, f"khong co ngoai le {exc_id}")
            if exc["status"] != "open":
                raise HTTPException(409, f"ngoai le nay da o trang thai '{exc['status']}'")

            # Pham vi ap ca o day — khong duoc sua dong ngoai pham vi.
            if not p.unrestricted and exc["state"] not in p.scope_states:
                raise HTTPException(403, f"ban khong co pham vi tren bang {exc['state']}")

            key = (exc["year"], exc["state"], exc["gender"], exc["name"])

            if body.action == "apply":
                cur.execute(
                    """SELECT version, new_value FROM fact_override
                       WHERE year=%s AND state=%s AND gender=%s AND name=%s AND field='number'
                       FOR UPDATE""", key)
                existing = cur.fetchone()
                current_version = existing["version"] if existing else 0

                # --- khoa lac quan ---
                if current_version != body.expected_version:
                    cur.execute(
                        """SELECT number FROM fact_current
                           WHERE year=%s AND state=%s AND gender=%s AND name=%s""", key)
                    base = cur.fetchone()
                    raise HTTPException(409, {
                        "loi": "co nguoi khac vua sua dong nay",
                        "expected_version": body.expected_version,
                        "current_version": current_version,
                        "gia_tri_goc": base["number"] if base else None,
                        "gia_tri_hien_tai": int(existing["new_value"]) if existing else None,
                        "gia_tri_ban_muon_ghi": body.new_value,
                    })

                cur.execute(
                    """SELECT number FROM fact_current
                       WHERE year=%s AND state=%s AND gender=%s AND name=%s""", key)
                base = cur.fetchone()
                if not base:
                    raise HTTPException(404, "dong du lieu khong con ton tai")

                cur.execute(
                    """INSERT INTO fact_override
                           (year, state, gender, name, field, old_value, new_value,
                            reason, version, created_by)
                       VALUES (%s,%s,%s,%s,'number',%s,%s,%s,%s,%s)
                       ON CONFLICT (year, state, gender, name, field) DO UPDATE SET
                           old_value = EXCLUDED.old_value,
                           new_value = EXCLUDED.new_value,
                           reason = EXCLUDED.reason,
                           version = fact_override.version + 1,
                           created_by = EXCLUDED.created_by,
                           created_at = now()
                       RETURNING version""",
                    (*key, str(base["number"]), str(body.new_value),
                     body.reason, current_version + 1, p.email))
                new_version = cur.fetchone()["version"]

                audit(cur, p.email, "override", "fact", "/".join(map(str, key)),
                      {"number": base["number"]}, {"number": body.new_value, "ly_do": body.reason})
                new_status = "applied"
            else:
                new_version = body.expected_version
                audit(cur, p.email, body.action, "qc_exception", str(exc_id),
                      {"status": "open"}, {"status": body.action, "ly_do": body.reason})
                new_status = "parked" if body.action == "park" else "sent_back"

            cur.execute(
                """UPDATE qc_exception SET status=%s, resolved_at=now(), resolved_by=%s
                   WHERE id=%s""", (new_status, p.email, exc_id))
        conn.commit()

    return {"id": exc_id, "status": new_status, "version": new_version}


# ---------------------------------------------------------------- release

class ReleaseBody(BaseModel):
    label: str = Field(min_length=3)


@app.post("/api/release")
def release(body: ReleaseBody, p: Me) -> dict:
    p.require("team_lead", "admin")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM qc_exception WHERE status='open' AND severity='critical'")
            blocking = cur.fetchone()["n"]
            if blocking:
                # Cong phat hanh: con ngoai le nghiem trong thi khong ky duoc.
                raise HTTPException(409, {
                    "loi": "cong phat hanh dang khoa",
                    "ngoai_le_nghiem_trong_con_mo": blocking,
                })

            cur.execute("SELECT last_run_id, last_row_count FROM sync_state WHERE id=1")
            st = cur.fetchone()
            if not st or not st["last_run_id"]:
                raise HTTPException(409, "chua co lan dong bo nao de ky")

            cur.execute(
                """INSERT INTO signed_version (run_id, label, row_count, signed_by)
                   VALUES (%s,%s,%s,%s) RETURNING id, signed_at""",
                (st["last_run_id"], body.label, st["last_row_count"], p.email))
            sv = cur.fetchone()
            audit(cur, p.email, "release", "signed_version", str(sv["id"]),
                  None, {"run_id": st["last_run_id"], "label": body.label})
        conn.commit()

    return {"id": sv["id"], "run_id": st["last_run_id"], "label": body.label,
            "row_count": st["last_row_count"], "signed_at": sv["signed_at"].isoformat()}


@app.get("/api/gate")
def gate(p: Me) -> dict:
    """Trang thai cong phat hanh — giao dien doc de hien banner."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT severity, count(*) AS n FROM qc_exception
                       WHERE status='open' GROUP BY severity""")
        counts = {r["severity"]: r["n"] for r in cur.fetchall()}
        cur.execute("""SELECT id, label, run_id, signed_by, signed_at
                       FROM signed_version ORDER BY id DESC LIMIT 1""")
        last = cur.fetchone()
    blocking = counts.get("critical", 0)
    return {"locked": blocking > 0, "blocking": blocking, "open_by_severity": counts,
            "last_signed": last}


# ---------------------------------------------------------------- exports

class ExportBody(BaseModel):
    format: str = "csv"


@app.post("/api/exports", status_code=202)
def create_export(body: ExportBody, p: Me) -> dict:
    if body.format not in {"csv", "xlsx"}:
        raise HTTPException(400, "format phai la csv hoac xlsx")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM qc_exception WHERE status='open' AND severity='critical'")
            if cur.fetchone()["n"]:
                raise HTTPException(409, "cong phat hanh dang khoa, khong tai file duoc")

            cur.execute("SELECT last_run_id FROM sync_state WHERE id=1")
            st = cur.fetchone()
            cur.execute(
                """INSERT INTO export_job (run_id, status, requested_by)
                   VALUES (%s, 'pending', %s) RETURNING id, created_at""",
                (st["last_run_id"] if st else "?", p.email))
            job = cur.fetchone()
            audit(cur, p.email, "export_request", "export_job", str(job["id"]),
                  None, {"format": body.format})
        conn.commit()

    return {"job_id": job["id"], "status": "pending",
            "created_at": job["created_at"].isoformat(),
            "note": "Export Job thuc thi o P6"}


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
            "gcs_path": job["gcs_path"], "error": job["error"]}


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

    Bo loc tren thanh cong cu duoc ap vao phan dem dong va dem ngoai le;
    cong phat hanh va ban da ky thi luon la toan cuc — ky la ky ca bo
    du lieu, khong ky rieng mot bang.
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

        # Ngoai le: cung bo loc, nhung khoa cua ngoai le co the NULL
        # (luat theo nhom nhu thi_phan_khong_tron_100 khong gan vao mot ten).
        extra = f" AND {' AND '.join(where)}" if where else ""

        cur.execute(
            f"""SELECT severity, count(*) AS n FROM qc_exception
                WHERE status='open'{extra} GROUP BY severity""", params)
        by_severity = {r["severity"]: r["n"] for r in cur.fetchall()}

        cur.execute(
            f"""SELECT rule_id, severity, count(*) AS n FROM qc_exception
                WHERE status='open'{extra} GROUP BY rule_id, severity ORDER BY n DESC""", params)
        by_rule = cur.fetchall()

        cur.execute(
            f"""SELECT state, count(*) AS n FROM qc_exception
                WHERE status='open' AND state IS NOT NULL{extra}
                GROUP BY state ORDER BY n DESC LIMIT 12""", params)
        by_state = cur.fetchall()

        cur.execute(
            f"SELECT count(*) AS n FROM qc_exception WHERE status <> 'open'{extra}", params)
        resolved = cur.fetchone()["n"]

        # So dong bi gan co = so khoa tu nhien khac nhau dang co ngoai le mo.
        cur.execute(
            f"""SELECT count(DISTINCT (year, state, gender, name)) AS n FROM qc_exception
                WHERE status='open' AND name IS NOT NULL{extra}""", params)
        flagged = cur.fetchone()["n"]

        ov_scope, ov_params = scope_clause(p, state)
        cur.execute(
            f"""SELECT count(*) AS n FROM fact_override
                {f'WHERE {ov_scope}' if ov_scope else ''}""", ov_params)
        overrides = cur.fetchone()["n"]

        # Cong phat hanh la TOAN CUC: no khoa ca bo du lieu chu khong khoa
        # rieng pham vi cua ai. Analyst Texas phai thay dung con so dang
        # chan phat hanh, ke ca khi ngoai le nam o bang khac.
        cur.execute("""SELECT count(*) AS n FROM qc_exception
                       WHERE status='open' AND severity='critical'""")
        blocking = cur.fetchone()["n"]

        cur.execute("""SELECT last_run_id, last_synced_at, last_row_count, status
                       FROM sync_state WHERE id = 1""")
        sync = cur.fetchone()
        cur.execute("""SELECT id, label, run_id, row_count, signed_by, signed_at
                       FROM signed_version ORDER BY id DESC LIMIT 1""")
        signed = cur.fetchone()

        since = 0
        if signed:
            cur.execute("SELECT count(*) AS n FROM fact_override WHERE created_at > %s",
                        (signed["signed_at"],))
            since = cur.fetchone()["n"]

    rows_now = sync["last_row_count"] if sync else None
    return {
        "scope": "tat ca" if p.unrestricted else sorted(p.scope_states),
        "filters": {"state": state, "year": year, "gender": gender},
        "facts": facts,
        "exceptions": {"open": sum(by_severity.values()), "by_severity": by_severity,
                       "by_rule": by_rule, "by_state": by_state,
                       "resolved": resolved, "flagged_rows": flagged},
        "overrides": overrides,
        "gate": {"locked": blocking > 0, "blocking": blocking},
        "last_signed": signed,
        "delta": {
            # Chenh lech so voi ban da ky gan nhat — cai nguoi duyet can
            # biet truoc khi ky ban tiep theo.
            "run_changed": bool(signed and sync and signed["run_id"] != sync["last_run_id"]),
            "rows_signed": signed["row_count"] if signed else None,
            "rows_now": rows_now,
            "rows_delta": (rows_now - signed["row_count"]) if signed and rows_now else None,
            "overrides_since": since,
        },
        "sync": sync,
    }


# ------------------------------------------------------- chi tiet ngoai le

@app.get("/api/exceptions/{exc_id}")
def exception_detail(exc_id: int, p: Me) -> dict:
    """Tat ca thu panel dieu tra can, trong MOT lan goi.

    Quan trong nhat la `expected_version`: client phai gui lai dung so
    nay khi ap so moi, neu khong khoa lac quan se tu choi.
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM qc_exception WHERE id = %s", (exc_id,))
        exc = cur.fetchone()
        if not exc:
            raise HTTPException(404, f"khong co ngoai le {exc_id}")
        if not p.unrestricted and exc["state"] not in p.scope_states:
            raise HTTPException(403, f"ban khong co pham vi tren bang {exc['state']}")

        key = (exc["year"], exc["state"], exc["gender"], exc["name"])
        fact = override = None
        history: list = []
        if all(k is not None for k in key):
            cur.execute(
                """SELECT year, state, gender, name, run_id, number, market_share,
                          prev_number, prev_year
                   FROM fact_current
                   WHERE year=%s AND state=%s AND gender=%s AND name=%s""", key)
            fact = cur.fetchone()
            cur.execute(
                """SELECT old_value, new_value, reason, version, created_by, created_at
                   FROM fact_override
                   WHERE year=%s AND state=%s AND gender=%s AND name=%s AND field='number'""", key)
            override = cur.fetchone()
            cur.execute(
                """SELECT actor, action, before, after, created_at FROM audit_log
                   WHERE entity_key = %s ORDER BY id DESC LIMIT 10""",
                ("/".join(map(str, key)),))
            history = cur.fetchall()

        cur.execute("""SELECT id, label, run_id, row_count, signed_by, signed_at
                       FROM signed_version ORDER BY id DESC LIMIT 1""")
        signed = cur.fetchone()

    return {"exception": exc, "fact": fact, "override": override,
            "expected_version": override["version"] if override else 0,
            "last_signed": signed, "history": history}


# --------------------------------------------------------------- versions

@app.get("/api/versions")
def versions(p: Me, limit: int = Query(50, ge=1, le=200)) -> dict:
    """Danh sach ban da ky — ai ky, luc nao, da gui cho ai."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id, run_id, label, row_count, signed_by, signed_at
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
        cur.execute(f"""SELECT id, run_id, status, requested_by, created_at,
                               finished_at, gcs_path, error
                        FROM export_job {where} ORDER BY id DESC LIMIT %s""", [*params, limit])
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
        cur.execute(
            "SELECT count(*) AS n FROM qc_exception WHERE status='open' AND severity='critical'")
        if cur.fetchone()["n"]:
            raise HTTPException(409, "cong phat hanh dang khoa, khong tai file duoc")

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
    if not settings.gcp_project_id:
        raise HTTPException(503, "chua cau hinh GCP_PROJECT_ID — chi chay duoc tren Cloud Run")

    url = (f"https://run.googleapis.com/v2/projects/{settings.gcp_project_id}"
           f"/locations/{settings.region}/jobs/{settings.sync_job_name}:run")
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        res = AuthorizedSession(creds).post(url, timeout=20)
        if res.status_code >= 300:
            raise HTTPException(502, f"Cloud Run tu choi: {res.status_code} {res.text[:300]}")
        operation = res.json().get("name", "")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"khong goi duoc Sync Job: {exc}") from exc

    with db() as conn:
        with conn.cursor() as cur:
            audit(cur, p.email, "rebuild", "sync_job", settings.sync_job_name, None,
                  {"operation": operation})
        conn.commit()
    return {"job": settings.sync_job_name, "operation": operation,
            "note": "Sync Job dang chay — banner do tuoi se doi khi xong"}
