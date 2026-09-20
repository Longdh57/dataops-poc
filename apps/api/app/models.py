"""Schema Postgres — toan bo bang cua ung dung.

Ghi chu thiet ke quan trong: fact_current bi DOI TEN moi lan sync
(staging -> current), nen id cua no KHONG on dinh. Moi bang tham chieu
toi mot dong fact phai dung KHOA TU NHIEN (year, state, gender, name),
khong duoc dung khoa ngoai toi fact_current.id.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer,
    JSON, String, Text, UniqueConstraint, func,
)
from sqlalchemy import desc as sa_text_desc
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FactCurrent(Base):
    """Ban sao doc tu BigQuery. Bang nay bi THAY THE NGUYEN KHOI moi lan sync.

    KHONG co cot id tu tang. Ly do: sync tao bang staging bang
    CREATE TABLE ... (LIKE fact_current INCLUDING ALL), viec nay copy ca
    default nextval() tro vao sequence cua bang goc. Sau khi doi ten,
    bang cu khong drop duoc vi sequence van bi bang moi tham chieu.
    Khoa tu nhien giai quyet triet de va cung la khoa that cua du lieu.
    """
    __tablename__ = "fact_current"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(8), primary_key=True)
    gender: Mapped[str] = mapped_column(String(1), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), primary_key=True)

    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    market_share: Mapped[float | None] = mapped_column(Float)
    prev_number: Mapped[int | None] = mapped_column(BigInteger)
    prev_year: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        # Bo loc thuong dung nhat cua giao dien: state + year + gender,
        # sap xep theo number giam dan. Index gop ca loc lan sap xep nen
        # planner khong phai quet nguoc roi loc bo.
        Index("ix_fact_filter_sort", "state", "year", "gender",
              sa_text_desc("number")),
        Index("ix_fact_year_gender", "year", "gender"),
        Index("ix_fact_name", "name"),
    )


class FactOverride(Base):
    """So da duoc nguoi dung sua tay. Merge de len fact_current luc doc."""
    __tablename__ = "fact_override"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # khoa tu nhien — KHONG dung FK toi fact_current.id
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(8), nullable=False)
    gender: Mapped[str] = mapped_column(String(1), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    field: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("year", "state", "gender", "name", "field", name="uq_override_key"),
        Index("ix_override_key", "year", "state", "gender", "name"),
    )


class QcException(Base):
    """Ngoai le do rule engine sinh ra. Vong doi: open -> applied/parked/sent_back."""
    __tablename__ = "qc_exception"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)

    year: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str | None] = mapped_column(String(8))
    gender: Mapped[str | None] = mapped_column(String(1))
    name: Mapped[str | None] = mapped_column(String(128))

    message: Mapped[str] = mapped_column(Text, nullable=False)
    observed: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(320))

    __table_args__ = (
        Index("ix_qc_status_severity", "status", "severity"),
        Index("ix_qc_run", "run_id"),
        Index("ix_qc_key", "year", "state", "gender", "name"),
    )


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppRole(Base):
    """Vai tro + pham vi du lieu. Pham vi LUON ap o tang server."""
    __tablename__ = "app_role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # analyst|team_lead|sale|admin
    # danh sach bang duoc xem; rong = xem tat ca
    scope_states: Mapped[list | None] = mapped_column(JSON)

    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_user_role"),)


class SignedVersion(Base):
    """Ban so lieu da ky — dong bang vinh vien."""
    __tablename__ = "signed_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Danh sach run_id CUA DU LIEU (team Data dat) co trong ban ky nay.
    # Khac han run_id o tren: cai do la nhan mot luot dong bo do Sync Job
    # tu sinh. Export phai loc theo danh sach nay, neu khong file gui khach
    # se chua ca nhung lan nap chua ai duyet.
    source_run_ids: Mapped[list | None] = mapped_column(JSON)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64))
    signed_by: Mapped[str] = mapped_column(String(320), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VersionsSent(Base):
    """Da gui ban nao cho khach nao ngay nao."""
    __tablename__ = "versions_sent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signed_version_id: Mapped[int] = mapped_column(
        ForeignKey("signed_version.id", ondelete="RESTRICT"), nullable=False)
    customer: Mapped[str] = mapped_column(String(256), nullable=False)
    sent_by: Mapped[str] = mapped_column(String(320), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    file_path: Mapped[str | None] = mapped_column(Text)


class ExportJob(Base):
    """Mot yeu cau xuat file. Job nen chay sau, khong nam tren duong request.

    Ba cot duoi day quyet dinh NOI DUNG file, va deu duoc chot o thoi diem
    xin file chu khong phai luc job chay: ban ky nao, dinh dang gi, va pham
    vi cua nguoi xin. Nguoi xin bi doi pham vi sau do thi file da phat ra
    van giai thich duoc.
    """
    __tablename__ = "export_job"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    signed_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("signed_version.id", ondelete="RESTRICT"))
    format: Mapped[str] = mapped_column(String(8), nullable=False, default="csv")
    # rong/NULL = khong gioi han bang
    scope_states: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    requested_by: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gcs_path: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    # Canh bao khong lam job that bai — vi du vuot gioi han dong cua Excel.
    warning: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class SyncState(Base):
    """Mot dong duy nhat (id=1). Banner do tuoi doc tu day."""
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_run_id: Mapped[str | None] = mapped_column(String(64))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_row_count: Mapped[int | None] = mapped_column(BigInteger)
    # dau van tay cua nguon: last_modified_time cua bang BigQuery
    source_last_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_row_count: Mapped[int | None] = mapped_column(BigInteger)
    # Nhung run_id cua du lieu dang nam trong ban sao. Ky phat hanh se
    # dong bang danh sach nay vao signed_version.
    source_run_ids: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="idle")
    last_error: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    """Moi thao tac deu de lai dau vet. Khong bao gio xoa."""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(320), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_key: Mapped[str | None] = mapped_column(String(256))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_audit_created", "created_at"),
        Index("ix_audit_entity", "entity", "entity_key"),
    )
