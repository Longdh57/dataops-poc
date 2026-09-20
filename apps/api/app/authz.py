"""Phan quyen: vao roi thi lam duoc gi, thay duoc du lieu nao.

Nguyen tac khong duoc pha: PHAM VI DU LIEU LUON LAY TU DATABASE THEO
EMAIL, KHONG BAO GIO LAY TU THAM SO CLIENT. Client co the gui
?state=CA, nhung dieu kien that la GIAO giua tham so do va pham vi
duoc gan cho nguoi dung. Nguoi dung pham vi [TX] goi ?state=CA se nhan
ve rong, khong phai du lieu CA.
"""

from dataclasses import dataclass, field

from fastapi import HTTPException


@dataclass
class Principal:
    email: str
    display_name: str | None = None
    roles: set[str] = field(default_factory=set)
    # rong = xem tat ca cac bang
    scope_states: set[str] = field(default_factory=set)

    @property
    def unrestricted(self) -> bool:
        return not self.scope_states

    def has(self, *roles: str) -> bool:
        return bool(self.roles & set(roles))

    def require(self, *roles: str) -> None:
        if not self.has(*roles):
            raise HTTPException(
                403, f"can vai tro {' hoac '.join(roles)}; ban co {sorted(self.roles) or 'khong co'}"
            )


def load_principal(conn, email: str) -> Principal:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, email, display_name, is_active FROM app_user WHERE lower(email) = %s",
            (email,),
        )
        user = cur.fetchone()
        if not user:
            raise HTTPException(403, f"{email} chua duoc cap quyen vao he thong")
        if not user["is_active"]:
            raise HTTPException(403, f"{email} da bi vo hieu hoa")

        cur.execute("SELECT role, scope_states FROM app_role WHERE user_id = %s", (user["id"],))
        rows = cur.fetchall()

    roles: set[str] = set()
    scope: set[str] = set()
    unrestricted = False
    for r in rows:
        roles.add(r["role"])
        states = r["scope_states"]
        if not states:
            # mot vai tro khong gioi han -> nguoi nay xem duoc tat ca
            unrestricted = True
        else:
            scope.update(s.upper() for s in states)

    return Principal(
        email=user["email"],
        display_name=user["display_name"],
        roles=roles,
        scope_states=set() if unrestricted else scope,
    )


def scope_clause(p: Principal, requested_state: str | None,
                 alias: str = "") -> tuple[str, list]:
    """Sinh dieu kien WHERE ep pham vi.

    `alias` la tien to bang, bat buoc khi cau truy van co JOIN — ca
    fact_current lan fact_override deu co cot `state`, khong ghi ro bang
    thi Postgres bao "column reference is ambiguous".

    Tra ve ("", []) khi khong can gioi han gi.
    Tra ve ("1 = 0", []) khi nguoi dung xin bang ngoai pham vi — ket qua
    rong, khong phai loi 403, de khong ro ri thong tin bang nao ton tai.
    """
    col = f"{alias}.state" if alias else "state"
    want = requested_state.upper() if requested_state else None

    if p.unrestricted:
        return (f"{col} = %s", [want]) if want else ("", [])

    if want:
        if want not in p.scope_states:
            return ("1 = 0", [])
        return (f"{col} = %s", [want])

    allowed = sorted(p.scope_states)
    return (f"{col} = ANY(%s)", [allowed])
