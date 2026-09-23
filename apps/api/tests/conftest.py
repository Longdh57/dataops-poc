import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://dataops:dataops@localhost:5432/dataops")
os.environ.setdefault("REQUIRE_IAP", "false")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app import bq_snapshot
from app.main import app

ADMIN = "longbloginfo@gmail.com"
LEAD = "lead@dataops.test"
TX = "analyst.tx@dataops.test"
CA = "analyst.ca@dataops.test"


@pytest.fixture(autouse=True)
def bigquery_gia(monkeypatch):
    """Ky khong goi BigQuery that trong test.

    Ten gia van theo dung mau `snapshot_<epoch>`, them duoi ngau nhien vi
    cot bq_snapshot la UNIQUE ma test ky nhieu lan trong cung mot giay.
    """
    def freeze(signed_at, run_ids, expected_checksum, label, signed_by):
        return (f"test-project.dataops_signed."
                f"{bq_snapshot.table_name(signed_at)}_{uuid.uuid4().hex[:8]}")

    monkeypatch.setattr(bq_snapshot, "freeze", freeze)
    monkeypatch.setattr(bq_snapshot, "drop", lambda table_id: None)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def as_user(email: str) -> dict:
    return {"X-Dev-User": email}
