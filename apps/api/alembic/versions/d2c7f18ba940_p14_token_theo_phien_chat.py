"""p14: token theo tung phien chat AI Agent

Truoc P14 man hinh Agent chi co mot con so: token/chi phi Vertex AI ca
thang, doc tu Cloud Monitoring. So do la cua CA PROJECT, khong tach duoc
theo phien hay theo nguoi hoi, va tre 1-2 phut sau moi lenh goi.

Bang `agent_token_usage` giu so lay tu `usageMetadata` ma Vertex AI tra
ve ngay trong response cua tung lenh goi: chinh xac, co ngay, va gan
duoc vao session_id + email nguoi hoi.

Chi them bang moi, khong dung toi bang nao dang co — code cu chay binh
thuong voi schema nay.

Revision ID: d2c7f18ba940
Revises: a7d3e9c1b5f2
Create Date: 2026-09-25 11:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2c7f18ba940"
down_revision: Union[str, None] = "a7d3e9c1b5f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_token_usage",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # KHONG co khoa ngoai toi bang phien cua ADK: schema do ADK tu tao
        # va tu quan, Alembic khong dung toi.
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("user_email", sa.String(length=320), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_token_session", "agent_token_usage", ["session_id"])
    op.create_index("ix_agent_token_user", "agent_token_usage", ["user_email", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_token_user", table_name="agent_token_usage")
    op.drop_index("ix_agent_token_session", table_name="agent_token_usage")
    op.drop_table("agent_token_usage")
