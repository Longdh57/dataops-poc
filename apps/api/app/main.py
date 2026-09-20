"""Data Operations API — P3: phan quyen, override, cong phat hanh."""

import base64
import json
from datetime import datetime, timezone
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
            "scope_states": "tat ca" if p.unrestricted else sorted(p.scope_states)}


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
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    scope_sql, scope_params = scope_clause(p, state)
    where, params = ["status = %s"], [status]
    if scope_sql:
        where.append(scope_sql); params += list(scope_params)
    if severity:
        where.append("severity = %s"); params.append(severity)

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
