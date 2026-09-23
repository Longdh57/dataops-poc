"""p11: dong bang du lieu BigQuery luc ky

Truoc P11 ban ky chi giu danh sach run_id, con Export Job doc thang bang
fact dang song — team Data sua so tai cho thi file gui khach mang so
chua ai duyet. Tu P11 moi lan ky chup bang fact thanh mot table snapshot
`snapshot_<epoch>` va ghi table id vao cot moi duoi day; Export chi doc
tu snapshot.

Ban ky cu de NULL: du lieu cua chung khong con dong bang duoc nua, va
API tu choi xuat file tu chung thay vi lang le doc bang song.

Revision ID: a7d3e9c1b5f2
Revises: f4b82d6e1a37
Create Date: 2026-09-24 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7d3e9c1b5f2"
down_revision: Union[str, None] = "f4b82d6e1a37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("signed_version", sa.Column("bq_snapshot", sa.String(1024), nullable=True))
    op.create_unique_constraint("uq_signed_version_bq_snapshot", "signed_version",
                                ["bq_snapshot"])


def downgrade() -> None:
    op.drop_constraint("uq_signed_version_bq_snapshot", "signed_version", type_="unique")
    op.drop_column("signed_version", "bq_snapshot")
