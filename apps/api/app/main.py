"""Data Operations API — khung P0.

Chi co health check va /api/version de xac nhan duong day
web -> api -> postgres thong suot. Nghiep vu that thuoc P3.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import psycopg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import settings


def _db_status() -> dict:
    """Ping Postgres. Tra ve trang thai thay vi nem loi, de /health
    van tra loi duoc khi db chua san sang."""
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
        return {"connected": True, "server": version.split(",")[0]}
    except Exception as exc:  # noqa: BLE001 - health check khong duoc sap
        return {"connected": False, "error": str(exc)}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[api] khoi dong · db={settings.database_url.rsplit('@', 1)[-1]}")
    yield


app = FastAPI(title="Data Operations API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "dataops-api",
        "time": datetime.now(timezone.utc).isoformat(),
        "database": _db_status(),
    }


@app.get("/api/version")
def version() -> dict:
    """Banner do tuoi du lieu. P2 se thay bang doc that tu bang sync_state."""
    return {
        "run_id": None,
        "last_synced_at": None,
        "note": "chua co Sync Job — se duoc cai dat o P2",
    }
