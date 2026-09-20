"""p5: export theo ban ky, dinh dang va pham vi

Ba cau hoi ma bang export_job cu khong tra loi duoc:
  - file nay xuat tu ban ky nao?          -> signed_version_id
  - nguoi xin chon CSV hay Excel?         -> format
  - nguoi xin duoc xem nhung bang nao?    -> scope_states

Va mot cau hoi signed_version cu khong tra loi duoc: ban ky nay gom
nhung lan nap du lieu nao -> source_run_ids.

Revision ID: b1f4c27a90de
Revises: 6ccc8e79dbcd
Create Date: 2026-09-20 15:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1f4c27a90de"
down_revision: Union[str, None] = "6ccc8e79dbcd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sync_state", sa.Column("source_run_ids", sa.JSON(), nullable=True))
    op.add_column("signed_version", sa.Column("source_run_ids", sa.JSON(), nullable=True))

    op.add_column("export_job", sa.Column("signed_version_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_export_signed_version", "export_job", "signed_version",
                          ["signed_version_id"], ["id"], ondelete="RESTRICT")
    # server_default de cac dong cu khong vi pham NOT NULL; dong moi luon
    # duoc API ghi ro.
    op.add_column("export_job",
                  sa.Column("format", sa.String(length=8), nullable=False, server_default="csv"))
    op.add_column("export_job", sa.Column("scope_states", sa.JSON(), nullable=True))
    op.add_column("export_job", sa.Column("row_count", sa.BigInteger(), nullable=True))
    op.add_column("export_job", sa.Column("warning", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("export_job", "warning")
    op.drop_column("export_job", "row_count")
    op.drop_column("export_job", "scope_states")
    op.drop_column("export_job", "format")
    op.drop_constraint("fk_export_signed_version", "export_job", type_="foreignkey")
    op.drop_column("export_job", "signed_version_id")
    op.drop_column("signed_version", "source_run_ids")
    op.drop_column("sync_state", "source_run_ids")
