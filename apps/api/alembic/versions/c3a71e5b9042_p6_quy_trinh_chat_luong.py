"""p6: quy trinh chat luong — bo override, them ticket, ban ky ghi no

Doi lai ba cau tra loi ma schema cu khong dua ra duoc:

  - So trong file ban ra co khop voi BigQuery khong?
    -> bo han fact_override. Ung dung khong sua so nua.
  - Loi da bao cho team Data da duoc sua that chua?
    -> bang `ticket` mang `expected_value`, QC doi chieu moi lan nap.
  - Ban ky nay luc ky con no nhung gi, ai dung ten?
    -> signed_version.violations / violations_fingerprint / rules_version
       / open_tickets / approval_note, va checksum lan dau duoc ghi that.

Lich su override KHONG mat theo bang: moi lan ap so deu da duoc ghi vao
audit_log voi ca gia tri truoc lan sau.

Revision ID: c3a71e5b9042
Revises: b1f4c27a90de
Create Date: 2026-09-21 09:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3a71e5b9042"
down_revision: Union[str, None] = "b1f4c27a90de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. Ung dung thoi sua so ---------------------------------------
    op.drop_index("ix_override_key", table_name="fact_override")
    op.drop_table("fact_override")

    # --- 2. Vi pham thuoc ve dung mot lan nap ---------------------------
    # Quyet dinh khong con nam tren tung vi pham nua, nen ba cot nay het
    # y nghia. Chung tung la cho `park`/`send_back` dong ngoai le lai ma
    # du lieu van sai.
    op.drop_index("ix_qc_status_severity", table_name="qc_exception")
    op.drop_index("ix_qc_run", table_name="qc_exception")
    op.drop_column("qc_exception", "status")
    op.drop_column("qc_exception", "resolved_at")
    op.drop_column("qc_exception", "resolved_by")
    op.create_index("ix_qc_run_severity", "qc_exception", ["run_id", "severity"])

    # --- 3. Ticket ------------------------------------------------------
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
    # Mot o chi duoc co MOT ticket dang song — hai cai thi khong ai biet
    # dieu kien nghiem thu nao moi la that.
    op.create_index("uq_ticket_open_key", "ticket",
                    ["year", "state", "gender", "name", "field"], unique=True,
                    postgresql_where=sa.text("status IN ('open', 'awaiting_verify')"))
    op.create_index("ix_ticket_status", "ticket", ["status", "blocking"])

    # --- 4. Ban ky ghi ro mon no ----------------------------------------
    op.add_column("signed_version", sa.Column("violations", sa.JSON(), nullable=True))
    op.add_column("signed_version",
                  sa.Column("violations_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("signed_version", sa.Column("rules_version", sa.Integer(), nullable=True))
    op.add_column("signed_version", sa.Column("open_tickets", sa.JSON(), nullable=True))
    op.add_column("signed_version", sa.Column("approval_note", sa.Text(), nullable=True))

    # --- 5. QC ghi lai no da kiem gi, duoi bo luat nao -------------------
    op.add_column("sync_state", sa.Column("qc_run_id", sa.String(length=64), nullable=True))
    op.add_column("sync_state", sa.Column("qc_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sync_state", sa.Column("rules_version", sa.Integer(), nullable=True))

    # --- 6. File dau ban ky di kem deliverable ---------------------------
    op.add_column("export_job", sa.Column("stamp_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("export_job", "stamp_path")

    op.drop_column("sync_state", "rules_version")
    op.drop_column("sync_state", "qc_checked_at")
    op.drop_column("sync_state", "qc_run_id")

    op.drop_column("signed_version", "approval_note")
    op.drop_column("signed_version", "open_tickets")
    op.drop_column("signed_version", "rules_version")
    op.drop_column("signed_version", "violations_fingerprint")
    op.drop_column("signed_version", "violations")

    op.drop_index("ix_ticket_status", table_name="ticket")
    op.drop_index("uq_ticket_open_key", table_name="ticket")
    op.drop_table("ticket")

    op.drop_index("ix_qc_run_severity", table_name="qc_exception")
    op.add_column("qc_exception", sa.Column("resolved_by", sa.String(length=320), nullable=True))
    op.add_column("qc_exception", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("qc_exception",
                  sa.Column("status", sa.String(length=16), nullable=False, server_default="open"))
    op.create_index("ix_qc_run", "qc_exception", ["run_id"])
    op.create_index("ix_qc_status_severity", "qc_exception", ["status", "severity"])

    # Dung lai bang cu de rollback duoc, nhung du lieu override thi khong
    # quay ve: no da bi xoa cung bang. Dau vet con nguyen trong audit_log.
    op.create_table(
        "fact_override",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=8), nullable=False),
        sa.Column("gender", sa.String(length=1), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("year", "state", "gender", "name", "field", name="uq_override_key"),
    )
    op.create_index("ix_override_key", "fact_override", ["year", "state", "gender", "name"])
