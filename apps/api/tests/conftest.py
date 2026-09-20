import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://dataops:dataops@localhost:5432/dataops")
os.environ.setdefault("REQUIRE_IAP", "false")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.main import app

ADMIN = "longbloginfo@gmail.com"
LEAD = "lead@dataops.test"
TX = "analyst.tx@dataops.test"
CA = "analyst.ca@dataops.test"


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def as_user(email: str) -> dict:
    return {"X-Dev-User": email}
