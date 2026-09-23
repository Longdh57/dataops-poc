"""p10: bo luat QC song trong Postgres

Truoc P10 bo luat la file rules/rules.yaml duoc COPY vao ca image API lan
image jobs — doi mot nguong la build lai hai image roi deploy. Tu P10 bo
luat nam o ba bang duoi day va sua duoc ngay trong ung dung:

  qc_rule              mot dong = mot luat, id la slug bat bien
  qc_ruleset           mot dong (id=1): version toan cuc, +1 moi lan ghi
  qc_ruleset_snapshot  toan bo bo luat tai MOI version — ban ky cu tai
                       hien duoc dung bo luat da duyet

Migration nay SEED ba bang tu rules/rules.yaml (version trong file giu
nguyen, hien la 6) va ghi snapshot cho version do TRUOC khi ai kip sua.
Khong tim thay file thi DUNG han, khong tao bo luat rong: bo luat rong
nghia la QC chay ma khong bat gi, va man hinh bao "khong vi pham".

Chay lai tren database da co luat thi bo qua phan seed.

Revision ID: f4b82d6e1a37
Revises: e91a2c5f7b14
Create Date: 2026-09-23 10:00:00.000000
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4b82d6e1a37"
down_revision: Union[str, None] = "e91a2c5f7b14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_ACTOR = "migration:p10"


def upgrade() -> None:
    op.create_table(
        "qc_rule",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sql", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("severity IN ('critical', 'warning', 'info')", name="ck_qc_rule_severity"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "qc_ruleset",
        sa.Column("id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "qc_ruleset_snapshot",
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("version"),
    )
    _seed()


def _seed() -> None:
    conn = op.get_bind()
    if conn.execute(sa.text("SELECT count(*) FROM qc_rule")).scalar():
        return

    # Import o day chu khong o dau file: alembic env.py da dua app/ vao
    # sys.path, va rules_path() biet ca ba cho file luat co the nam.
    from app import rules as rules_file

    path = rules_file.rules_path()
    if path is None:
        raise RuntimeError(
            "p10: khong tim thay rules/rules.yaml de seed bo luat — dung migration. "
            "Image API phai kem thu muc rules/, hoac dat RULES_PATH.")
    catalog = rules_file.parse(path.read_text(encoding="utf-8"))
    if loi := rules_file.validate_catalog(catalog["rules"]):
        raise RuntimeError("p10: file seed co loi — " + "; ".join(loi))

    version = catalog["version"] or 1
    rows = []
    for i, r in enumerate(catalog["rules"]):
        rows.append({**r, "enabled": True, "sort_order": (i + 1) * 10})
        conn.execute(
            sa.text("""INSERT INTO qc_rule
                         (id, severity, scope, message, sql, enabled, sort_order,
                          created_by, updated_by)
                       VALUES (:id, :severity, CAST(:scope AS json), :message, :sql,
                               true, :sort_order, :actor, :actor)"""),
            {"id": r["id"], "severity": r["severity"],
             "scope": json.dumps(r["scope"]) if r["scope"] else None,
             "message": r["message"], "sql": r["sql"],
             "sort_order": (i + 1) * 10, "actor": SEED_ACTOR})

    note = f"seed tu {path.parent.name}/{path.name}"
    conn.execute(
        sa.text("""INSERT INTO qc_ruleset (id, version, updated_by, updated_at, note)
                   VALUES (1, :v, :actor, now(), :note)"""),
        {"v": version, "actor": SEED_ACTOR, "note": note})
    conn.execute(
        sa.text("""INSERT INTO qc_ruleset_snapshot (version, rules, created_by, note)
                   VALUES (:v, CAST(:rules AS json), :actor, :note)"""),
        {"v": version, "rules": json.dumps(rows), "actor": SEED_ACTOR, "note": note})


def downgrade() -> None:
    # Bo luat quay ve file rules/rules.yaml trong repo. Nhung gi da sua qua
    # giao dien MAT o day — xuat YAML tu hop "Bo luat QC" truoc khi ha.
    op.drop_table("qc_ruleset_snapshot")
    op.drop_table("qc_ruleset")
    op.drop_table("qc_rule")
