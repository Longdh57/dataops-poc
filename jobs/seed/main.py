"""Seed nguoi dung thu nghiem.

Pham vi trong plan la "quoc gia"; dataset nay la USA Names nen pham vi
la BANG. Y nghia khong doi: analyst chi thay duoc phan du lieu duoc gan.
"""

import os
import sys

import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dataops:dataops@localhost:5432/dataops")
OWNER = os.getenv("OWNER_EMAIL", "longbloginfo@gmail.com")

USERS = [
    (OWNER,                      "Chu he thong",      "admin",     None),
    ("lead@dataops.test",        "Team Lead",         "team_lead", None),
    ("analyst.tx@dataops.test",  "Analyst Texas",     "analyst",   ["TX"]),
    ("analyst.ca@dataops.test",  "Analyst California","analyst",   ["CA"]),
    ("sale@dataops.test",        "Sale",              "sale",      ["CA", "TX"]),
]


def main() -> int:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for email, name, role, scope in USERS:
                cur.execute(
                    """INSERT INTO app_user (email, display_name, is_active)
                       VALUES (%s, %s, true)
                       ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
                       RETURNING id""",
                    (email, name))
                uid = cur.fetchone()[0]
                cur.execute(
                    """INSERT INTO app_role (user_id, role, scope_states)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (user_id, role) DO UPDATE SET scope_states = EXCLUDED.scope_states""",
                    (uid, role, psycopg.types.json.Json(scope) if scope else None))
                print(f"[seed] {email:28} {role:10} pham vi: {scope or 'tat ca'}", flush=True)
        conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
