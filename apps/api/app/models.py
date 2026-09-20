"""Schema Postgres — toan bo bang cua ung dung.

Ghi chu thiet ke quan trong: fact_current bi DOI TEN moi lan sync
(staging -> current), nen id cua no KHONG on dinh. Moi bang tham chieu
toi mot dong fact phai dung KHOA TU NHIEN (year, state, gender, name),
khong duoc dung khoa ngoai toi fact_current.id.

Nguyen tac thu hai, tu docs/quy-trinh-chat-luong.md: ung dung nay KHONG
sua so. Khong co bang nao giu "so da sua tay" nua. Loi di ra ngoai bang
`ticket` de team Data sua o nguon, va QC xac minh lai o lan nap ke tiep.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer,
    JSON, String, Text, UniqueConstraint, func, text,
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


class QcException(Base):
    """Mot vi pham luat, thuoc ve DUNG MOT lan nap.

    Khong con cot `status`: quyet dinh khong nam o day nua. QC quet lai
    toan bo luat sau moi lan nap va thay the nguyen bo vi pham cua lan nap
    do; ai cho qua cai gi thi nam o `signed_version.approval_note`.
    """
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

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_qc_run_severity", "run_id", "severity"),
        Index("ix_qc_key", "year", "state", "gender", "name"),
    )


class Ticket(Base):
    """Mot loi da duoc xac nhan, giao cho team Data sua o NGUON.

    Khac voi vi pham QC o hai diem quyet dinh:

    - No song xuyen qua nhieu lan nap, vi loi chi het khi nguon that su doi.
    - No mang `expected_value` — dieu kien nghiem thu KIEM DUOC BANG MAY.
      Thieu no thi "da sua xong roi" chi la loi hua, va QC khong co cach
      nao doi chieu.

    Vong doi: open -> awaiting_verify (team Data bao da sua) -> closed, va
    chi QC moi duoc dong. Lech so thi bat nguoc ve open kem so doc duoc.
    """
    __tablename__ = "ticket"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # khoa tu nhien — KHONG dung FK toi fact_current.id
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(8), nullable=False)
    gender: Mapped[str] = mapped_column(String(1), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    field: Mapped[str] = mapped_column(String(64), nullable=False, default="number")

    title: Mapped[str] = mapped_column(Text, nullable=False)
    expected_value: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at_open: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    # Quyet dinh NGAY luc tao: khong phan loai thi hoac ban ra du lieu co
    # loi da biet, hoac tac vinh vien vi mot ticket nho.
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # rule_id neu ticket sinh ra tu mot vi pham QC; rong = nguoi tu phat hien
    from_rule_id: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")

    created_by: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    marked_fixed_by: Mapped[str | None] = mapped_column(String(320))
    marked_fixed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Dau vet cua lan QC kiem gan nhat — de nguoi doc biet vi sao ticket
    # van con mo ma khong phai mo lai lich su.
    last_checked_run_id: Mapped[str | None] = mapped_column(String(64))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_observed: Mapped[str | None] = mapped_column(Text)

    closed_run_id: Mapped[str | None] = mapped_column(String(64))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # Mot o chi duoc co MOT ticket dang song. Hai ticket cung o thi
        # khong ai biet cai nao la dieu kien nghiem thu that.
        Index("uq_ticket_open_key", "year", "state", "gender", "name", "field",
              unique=True,
              postgresql_where=text("status IN ('open', 'awaiting_verify')")),
        Index("ix_ticket_status", "status", "blocking"),
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
    """Ban so lieu da ky — dong bang vinh vien.

    Nhan thoi thi rong. Mot ban ky phai tu tra loi duoc: no gom du lieu
    nao, luc ky con no nhung gi, va ai dung ten cho mon no do.
    """
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

    # Van tay DU LIEU cua ban ky. Team Data sua so tai cho duoi cung mot
    # run_id la chuyen binh thuong — khi do nhan van the ma so da khac.
    # Chi cot nay phat hien duoc.
    checksum: Mapped[str | None] = mapped_column(String(64))

    # --- mon no duoc ghi ra, thay vi bi giau di ---
    # {rule_id: so o vi pham} luc ky
    violations: Mapped[dict | None] = mapped_column(JSON)
    # van tay tap khoa vi pham — phan biet "van 3 o cu" voi "3 o khac"
    violations_fingerprint: Mapped[str | None] = mapped_column(String(64))
    # version cua rules.yaml, de tai hien duoc da duyet duoi bo luat nao
    rules_version: Mapped[int | None] = mapped_column(Integer)
    # ticket chua dong tai thoi diem ky
    open_tickets: Mapped[list | None] = mapped_column(JSON)
    # Phieu duyet: vi sao van ky du con vi pham. Bat buoc khi co no.
    approval_note: Mapped[str | None] = mapped_column(Text)

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
    # File dau ban ky di kem: ky kem vi pham gi, ticket nao chua dong.
    # Tach rieng vi CSV khong cho nhet dong chu thich vao giua du lieu.
    stamp_path: Mapped[str | None] = mapped_column(Text)


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

    # QC Runner ghi ba cot nay. API doc de biet bo vi pham dang hien co
    # thuoc lan nap nao va duoc sinh ra duoi bo luat version bao nhieu —
    # ban ky cheo lai chung, neu khong thi "da duyet" khong tai hien duoc.
    qc_run_id: Mapped[str | None] = mapped_column(String(64))
    qc_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rules_version: Mapped[int | None] = mapped_column(Integer)


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
