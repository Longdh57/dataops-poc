"""p8: doi dataset sang FDIC Summary of Deposits

Doi han truc du lieu: tu "ten khai sinh" (year, state, gender, name, number,
market_share) sang "deposit ngan hang" (year, state, institution_id,
institution, deposit, deposit_share). Day la doi mien du lieu, khong phai
doi ten cot — ba bang duoi day bi DROP va tao lai voi hinh dang moi, du
lieu cu (baby-name) khong con y nghia trong mien moi nen khong migrate.

Khoa tu nhien rut tu BON phan xuong BA: (year, state, institution_id).
`institution_id` (CERT cua FDIC) la ID on dinh; `institution` (ten hien
thi) KHONG con nam trong khoa vi ten mot to chuc doi cach viet hoa/thuong
giua cac nam trong du lieu FDIC that (vi du "Keybank" 2022 vs "KeyBank" tu
2023, cung CERT) — dung ten lam khoa se tach nham mot to chuc thanh hai.

signed_version, audit_log, sync_state khong doi: chung chi giu JSON/text
khong phu thuoc hinh dang fact.

Revision ID: e91a2c5f7b14
Revises: c3a71e5b9042
Create Date: 2026-09-22 08:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e91a2c5f7b14"
down_revision: Union[str, None] = "c3a71e5b9042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. fact_current --------------------------------------------------
    op.drop_index("ix_fact_filter_sort", table_name="fact_current")
    op.drop_index("ix_fact_name", table_name="fact_current")
    op.drop_index("ix_fact_year_gender", table_name="fact_current")
    op.drop_table("fact_current")

    op.create_table(
        "fact_current",
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=8), nullable=False),
        sa.Column("institution_id", sa.Integer(), nullable=False),
        sa.Column("institution", sa.String(length=256), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("deposit", sa.BigInteger(), nullable=False),
        sa.Column("deposit_share", sa.Float(), nullable=True),
        sa.Column("prev_deposit", sa.BigInteger(), nullable=True),
        sa.Column("prev_year", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("year", "state", "institution_id"),
    )
    op.create_index("ix_fact_filter_sort", "fact_current",
                    ["state", "year", sa.literal_column("deposit DESC")], unique=False)
    op.create_index("ix_fact_institution", "fact_current", ["institution"], unique=False)

    # --- 2. qc_exception ----------------------------------------------------
    op.drop_index("ix_qc_run_severity", table_name="qc_exception")
    op.drop_index("ix_qc_key", table_name="qc_exception")
    op.drop_table("qc_exception")

    op.create_table(
        "qc_exception",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=8), nullable=True),
        sa.Column("institution_id", sa.Integer(), nullable=True),
        sa.Column("institution", sa.String(length=256), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("observed", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_qc_run_severity", "qc_exception", ["run_id", "severity"], unique=False)
    op.create_index("ix_qc_key", "qc_exception", ["year", "state", "institution_id"], unique=False)

    # --- 3. ticket ------------------------------------------------------
    op.drop_index("uq_ticket_open_key", table_name="ticket")
    op.drop_index("ix_ticket_status", table_name="ticket")
    op.drop_table("ticket")

    op.create_table(
        "ticket",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=8), nullable=False),
        sa.Column("institution_id", sa.Integer(), nullable=False),
        sa.Column("institution", sa.String(length=256), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False, server_default="deposit"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("expected_value", sa.Text(), nullable=False),
        sa.Column("observed_at_open", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("from_rule_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("marked_fixed_by", sa.String(length=320), nullable=True),
        sa.Column("marked_fixed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_run_id", sa.String(length=64), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observed", sa.Text(), nullable=True),
        sa.Column("closed_run_id", sa.String(length=64), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_ticket_open_key", "ticket",
                    ["year", "state", "institution_id", "field"], unique=True,
                    postgresql_where=sa.text("status IN ('open', 'awaiting_verify')"))
    op.create_index("ix_ticket_status", "ticket", ["status", "blocking"])


def downgrade() -> None:
    op.drop_index("ix_ticket_status", table_name="ticket")
    op.drop_index("uq_ticket_open_key", table_name="ticket")
    op.drop_table("ticket")
    op.create_table(
        "ticket",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=8), nullable=False),
        sa.Column("gender", sa.String(length=1), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False, server_default="number"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("expected_value", sa.Text(), nullable=False),
        sa.Column("observed_at_open", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("from_rule_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("marked_fixed_by", sa.String(length=320), nullable=True),
        sa.Column("marked_fixed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_run_id", sa.String(length=64), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observed", sa.Text(), nullable=True),
        sa.Column("closed_run_id", sa.String(length=64), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_ticket_open_key", "ticket",
                    ["year", "state", "gender", "name", "field"], unique=True,
                    postgresql_where=sa.text("status IN ('open', 'awaiting_verify')"))
    op.create_index("ix_ticket_status", "ticket", ["status", "blocking"])

    op.drop_index("ix_qc_key", table_name="qc_exception")
    op.drop_index("ix_qc_run_severity", table_name="qc_exception")
    op.drop_table("qc_exception")
    op.create_table(
        "qc_exception",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=8), nullable=True),
        sa.Column("gender", sa.String(length=1), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("observed", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_qc_run_severity", "qc_exception", ["run_id", "severity"], unique=False)
    op.create_index("ix_qc_key", "qc_exception", ["year", "state", "gender", "name"], unique=False)

    op.drop_index("ix_fact_institution", table_name="fact_current")
    op.drop_index("ix_fact_filter_sort", table_name="fact_current")
    op.drop_table("fact_current")
    op.create_table(
        "fact_current",
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=8), nullable=False),
        sa.Column("gender", sa.String(length=1), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("number", sa.BigInteger(), nullable=False),
        sa.Column("market_share", sa.Float(), nullable=True),
        sa.Column("prev_number", sa.BigInteger(), nullable=True),
        sa.Column("prev_year", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("year", "state", "gender", "name"),
    )
    op.create_index("ix_fact_filter_sort", "fact_current",
                    ["state", "year", "gender", sa.literal_column("number DESC")], unique=False)
    op.create_index("ix_fact_name", "fact_current", ["name"], unique=False)
    op.create_index("ix_fact_year_gender", "fact_current", ["year", "gender"], unique=False)
