"""Data Operations API.

P2: mo endpoint de xem duoc du lieu da dong bo tu BigQuery sang Postgres.
Phan quyen va IAP JWT thuoc P3.
"""

from datetime import datetime, timezone

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

from .settings import settings

app = FastAPI(title="Data Operations API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Chi cho phep sap xep theo cot trong danh sach nay — chan SQL injection
# qua ten cot. Khong bao gio noi chuoi tu tham so client vao ORDER BY.
SORTABLE = {"year", "state", "gender", "name", "number", "market_share"}


def db():
    return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=5)


@app.get("/health")
def health() -> dict:
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute("SELECT version() AS v")
            server = cur.fetchone()["v"].split(",")[0]
        database = {"connected": True, "server": server}
    except Exception as exc:  # noqa: BLE001
        database = {"connected": False, "error": str(exc)}

    return {
        "status": "ok",
        "service": "dataops-api",
        "time": datetime.now(timezone.utc).isoformat(),
        "database": database,
    }


@app.get("/api/version")
def version() -> dict:
    """Banner do tuoi du lieu."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT last_run_id, last_synced_at, last_row_count,
                   source_row_count, status, last_error
            FROM sync_state WHERE id = 1
        """)
        row = cur.fetchone()

    if not row:
        return {"run_id": None, "last_synced_at": None, "note": "chua sync lan nao"}

    synced = row["last_synced_at"]
    age = (datetime.now(timezone.utc) - synced).total_seconds() if synced else None
    return {
        "run_id": row["last_run_id"],
        "last_synced_at": synced.isoformat() if synced else None,
        "age_seconds": round(age) if age is not None else None,
        # Canh bao khi ban sao qua cu — rui ro lon nhat cua kien truc nay
        "stale": age is not None and age > 1800,
        "row_count": row["last_row_count"],
        "source_row_count": row["source_row_count"],
        "status": row["status"],
        "error": row["last_error"],
    }


@app.get("/api/schema")
def schema() -> dict:
    """Liet ke toan bo bang trong Postgres kem so dong — de nhin thay schema."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT c.relname AS table_name,
                   c.reltuples::bigint AS est_rows,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS size
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            ORDER BY c.relname
        """)
        tables = cur.fetchall()

        # reltuples = -1 nghia la bang chua tung duoc ANALYZE, khong phai
        # "-1 dong". Nhung bang do deu nho nen dem that duoc.
        for t in tables:
            if t["est_rows"] is None or t["est_rows"] < 0:
                cur.execute(f'SELECT count(*) AS n FROM "{t["table_name"]}"')
                t["est_rows"] = cur.fetchone()["n"]
                t["exact"] = True
            else:
                t["exact"] = False

        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'fact_current'
            ORDER BY ordinal_position
        """)
        fact_columns = cur.fetchall()

        cur.execute("""
            SELECT indexname, indexdef FROM pg_indexes
            WHERE tablename = 'fact_current' ORDER BY indexname
        """)
        fact_indexes = cur.fetchall()

    return {"tables": tables, "fact_current": {"columns": fact_columns, "indexes": fact_indexes}}


@app.get("/api/facts")
def facts(
    state: str | None = None,
    year: int | None = None,
    gender: str | None = None,
    sort: str = Query("number", description="cot sap xep"),
    desc: bool = True,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    if sort not in SORTABLE:
        raise HTTPException(400, f"khong sap xep duoc theo '{sort}'")

    where, params = [], []
    if state:
        where.append("state = %s"); params.append(state)
    if year:
        where.append("year = %s"); params.append(year)
    if gender:
        where.append("gender = %s"); params.append(gender)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    direction = "DESC" if desc else "ASC"

    with db() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) AS n FROM fact_current {clause}", params)
        total = cur.fetchone()["n"]
        cur.execute(
            f"""SELECT year, state, gender, name, number, market_share,
                       prev_number, prev_year, run_id
                FROM fact_current {clause}
                ORDER BY {sort} {direction}
                LIMIT %s OFFSET %s""",
            [*params, limit, offset],
        )
        rows = cur.fetchall()

    return {"total": total, "limit": limit, "offset": offset, "rows": rows}
