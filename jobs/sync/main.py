"""Sync Job — BigQuery -> Cloud SQL. Cai dat that o P2.

Luong: doc last_modified_time tu __TABLES__ (metadata, khong quet du lieu
nen khong tinh phi) -> neu doi thi EXPORT DATA ra parquet tren GCS ->
COPY vao bang staging -> doi ten bang trong transaction (khong downtime).
"""

import sys


def main() -> int:
    print("[sync] khung P0 — logic that thuoc P2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
